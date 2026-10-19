"""T-DIFF-01, T-APP-01..04, T-APR-01..03, T-VAL-01..05."""

import ast
import os
from dataclasses import replace
from pathlib import Path

import pytest

from codemind import config
from codemind.agents.critic_validator import CriticValidatorAgent
from codemind.ingestion.zip_loader import rehash_snapshot, zip_directory
from codemind.models import FileEdit, ValidationStatus as V, WorkflowState as S, compute_patch_hash
from codemind.orchestrator.orchestrator import Orchestrator
from codemind.patching import fixers
from codemind.patching.apply import PatchScopeError, apply_to_copy
from codemind.patching.approval import ApprovalError, record
from codemind.validation import sandbox_runner
from tests.helpers import SAMPLE, make_zip


@pytest.fixture
def orch(tmp_path):
    o = Orchestrator(workspace_root=tmp_path / "ws")
    o.load_sample()
    o.analyze()
    assert o.ctx.state is S.FINDINGS_READY
    return o


def fid(o, rule):
    return next(f.id for f in o.ctx.findings if f.rule_id == rule)


def run_dirs(o):
    return sorted(p.name for p in o.ctx.snapshot.root.parent.iterdir())


# ---------------------------------------------------------------- diffs / fixers

@pytest.mark.parametrize("rule,removed,added", [
    ("R001", None, "    if not scores:"),
    ("R004", "-def add_score(score, history=[]):", "+def add_score(score, history=None):"),
    ("R007", "f\"SELECT", "(name,))"),
    ("R003", "-    return eval(raw)", "+    return ast.literal_eval(raw)"),
    ("R009", "-    if score == None:", "+    if score is None:"),
])
def test_proposal_diff_contents(orch, rule, removed, added):
    orch.select_finding(fid(orch, rule))
    p = orch.ctx.current_proposal
    assert p.affected_files == [orch.ctx.finding(p.finding_id).file]
    assert p.unified_diff.startswith(f"--- a/{p.affected_files[0]}\n+++ b/{p.affected_files[0]}")
    if removed:
        assert removed in p.unified_diff
    assert added in p.unified_diff
    ast.parse(p.edits[0].new_content)
    assert orch.ctx.state is S.AWAITING_APPROVAL


def test_no_automatic_fix_returns_to_findings(orch):
    orch.select_finding(fid(orch, "R008"))
    assert orch.ctx.state is S.FINDINGS_READY
    assert orch.ctx.decisions[-1].event == "no_fix_available"
    assert not orch.ctx.proposals


def test_fixers_refuse_unsafe_patterns():
    f = type("F", (), {"line": 2, "extra": {"call": "subprocess.run"}, "symbol": ""})()
    with pytest.raises(fixers.NoFix):
        fixers.r005_arg_list("import subprocess\nsubprocess.run('ls | grep x', shell=True)\n", f)


# ----------------------------------------------------------- reject / approve

def test_reject_leaves_original_and_creates_no_copy(orch):
    before = rehash_snapshot(orch.ctx.snapshot)
    dirs_before = run_dirs(orch)
    orch.select_finding(fid(orch, "R002"))
    p = orch.ctx.current_proposal
    orch.reject(p.patch_id, p.patch_hash)
    assert orch.ctx.state is S.FINDINGS_READY
    assert rehash_snapshot(orch.ctx.snapshot) == before == orch.ctx.snapshot.snapshot_hash
    assert run_dirs(orch) == dirs_before                       # no working copy for a rejected patch
    assert orch.ctx.approvals[-1].decision == "rejected"


def test_approve_changes_only_the_copy(orch):
    orch.select_finding(fid(orch, "R004"))
    p = orch.ctx.current_proposal
    orch.approve(p.patch_id, p.patch_hash)
    v = orch.ctx.latest_validation
    copy = Path(v.working_copy)
    assert "history=None" in (copy / "grades/stats.py").read_text()
    assert "history=[]" in (orch.ctx.snapshot.root / "grades/stats.py").read_text()
    assert v.original_unchanged is True
    assert not os.stat(orch.ctx.snapshot.root / "grades/stats.py").st_mode & 0o222
    assert orch.ctx.state is S.VALIDATED and v.status is V.PASSED
    assert v.tests_passed == 8 and v.tests_failed == 1        # 1 pre-existing failure, unrelated to R004
    assert any("pre-existing" in c.detail for c in v.checks)


def test_apply_refuses_without_valid_approval(orch):
    orch.select_finding(fid(orch, "R009"))
    with pytest.raises(ApprovalError):
        apply_to_copy(orch.ctx, orch.ctx.current_proposal)


# --------------------------------------------------------------- stale approval

def test_approval_with_wrong_hash_is_refused(orch):
    orch.select_finding(fid(orch, "R009"))
    p = orch.ctx.current_proposal
    with pytest.raises(ApprovalError, match="hash"):
        orch.approve(p.patch_id, "0" * 64)
    assert orch.ctx.state is S.AWAITING_APPROVAL


def test_old_approval_cannot_authorise_a_newer_proposal(orch):
    orch.select_finding(fid(orch, "R009"))
    old = orch.ctx.current_proposal
    orch.reject(old.patch_id, old.patch_hash)
    orch.select_finding(fid(orch, "R004"))
    new = orch.ctx.current_proposal
    with pytest.raises(ApprovalError, match="superseded"):
        orch.approve(old.patch_id, old.patch_hash)
    with pytest.raises(ApprovalError):
        orch.approve(new.patch_id, old.patch_hash)          # A's hash for B
    assert orch.ctx.state is S.AWAITING_APPROVAL


def test_tampered_proposal_is_refused(orch):
    orch.select_finding(fid(orch, "R009"))
    p = orch.ctx.current_proposal
    p.edits[0] = replace(p.edits[0], new_content=p.edits[0].new_content + "import os\n")
    with pytest.raises(ApprovalError, match="changed"):
        orch.approve(p.patch_id, p.patch_hash)


def test_changed_original_invalidates_approval(orch):
    orch.select_finding(fid(orch, "R009"))
    p = orch.ctx.current_proposal
    target = orch.ctx.snapshot.root / "grades/stats.py"
    target.chmod(0o644)
    target.write_text(target.read_text() + "\n# edited\n")
    with pytest.raises(ApprovalError, match="original source"):
        orch.approve(p.patch_id, p.patch_hash)


def test_out_of_scope_edit_rejected_by_critic_and_apply(orch):
    orch.select_finding(fid(orch, "R009"))
    p = orch.ctx.current_proposal
    other = next(f for f in orch.ctx.snapshot.included_files if f.rel_path == "grades/cli.py")
    p.edits.append(FileEdit("grades/cli.py", other.sha256, "print('sneaky')\n"))
    review = CriticValidatorAgent().review(orch.ctx, p)
    assert not review.in_scope and any("grades/cli.py" in i for i in review.issues)
    p.patch_hash = compute_patch_hash(p.edits, p.base_snapshot_hash)
    record(orch.ctx, p, "approved", p.patch_hash)
    with pytest.raises(PatchScopeError):
        apply_to_copy(orch.ctx, p)


def test_traversal_edit_rejected(orch):
    orch.select_finding(fid(orch, "R009"))
    p = orch.ctx.current_proposal
    p.edits[0] = FileEdit("../../evil.py", p.edits[0].original_sha256, "x = 1\n")
    p.affected_files = ["../../evil.py"]
    p.patch_hash = compute_patch_hash(p.edits, p.base_snapshot_hash)
    with pytest.raises(ApprovalError, match="unsafe patch path"):
        record(orch.ctx, p, "approved", p.patch_hash)
    with pytest.raises((ApprovalError, PatchScopeError)):
        apply_to_copy(orch.ctx, p)
    assert not (orch.ctx.snapshot.root.parent.parent / "evil.py").exists()


# ------------------------------------------------------------------ validation

def test_retry_after_real_failure_then_pass(orch):
    """T-VAL-01/02 + T-E2E core: strategy 1 fails the repo's own test, strategy 2 passes."""
    f = fid(orch, "R001")
    assert orch.ctx.finding(f).confidence.value == "Confirmed"
    orch.select_finding(f)
    first = orch.ctx.current_proposal
    assert first.strategy_name == "Return a safe default"
    orch.approve(first.patch_id, first.patch_hash)
    failed = orch.ctx.validations[-1]
    assert failed.status is V.FAILED and failed.tests_failed == 1
    assert any(c.outcome == "failed" and c.name.endswith("test_average_empty_raises") for c in failed.test_cases)
    assert orch.ctx.state is S.AWAITING_APPROVAL                # new proposal needs a NEW approval
    second = orch.ctx.current_proposal
    assert second.strategy_name == "Raise ValueError" and second.attempt == 2
    assert second.patch_hash != first.patch_hash
    orch.approve(second.patch_id, second.patch_hash)
    ok = orch.ctx.validations[-1]
    assert ok.status is V.PASSED and (ok.tests_passed, ok.tests_failed, ok.tests_errors) == (9, 0, 0)
    assert orch.ctx.state is S.VALIDATED


def test_retries_exhausted_blocks(orch, monkeypatch):
    monkeypatch.setattr(config, "MAX_RETRIES", 0)
    orch.select_finding(fid(orch, "R001"))
    p = orch.ctx.current_proposal
    orch.approve(p.patch_id, p.patch_hash)
    assert orch.ctx.state is S.BLOCKED
    assert "escalated" in orch.ctx.blocked_reason
    assert orch.ctx.decisions[-1].event == "retries_exhausted"


def test_syntax_failure_reported_and_tests_not_run(orch):
    orch.select_finding(fid(orch, "R009"))
    p = orch.ctx.current_proposal
    copy = orch.ctx.snapshot.root.parent / "manual_copy"
    from codemind.workspace import make_working_copy
    copy = make_working_copy(orch.ctx.snapshot, "manual")
    (copy / "grades/stats.py").write_text("def broken(:\n")
    r = CriticValidatorAgent().validate(orch.ctx, p, copy)
    status = {c.name: c.status for c in r.checks}
    assert r.status is V.FAILED and status["Syntax check"] is V.FAILED and status["Tests"] is V.NOT_RUN


def test_untrusted_upload_is_partially_verified(tmp_path):
    o = Orchestrator(workspace_root=tmp_path / "ws")
    o.load_zip(zip_directory(SAMPLE), "upload.zip", trusted=False)
    o.analyze()
    assert o.ctx.plan.step_status["baseline"] == "skipped" and o.ctx.baseline is None
    o.select_finding(next(f.id for f in o.ctx.findings if f.rule_id == "R009"))
    p = o.ctx.current_proposal
    o.approve(p.patch_id, p.patch_hash)
    v = o.ctx.latest_validation
    assert v.status is V.PARTIALLY_VERIFIED and o.ctx.state is S.PARTIALLY_VERIFIED
    assert {c.name: c.status for c in v.checks}["Tests"] is V.NOT_RUN
    assert v.tests_passed == 0


def test_timeout_is_blocked(tmp_path, monkeypatch):
    repo = {"README.md": "# Slow\n\nSlow tests.\n",
            "slow.py": "def f(x, items=[]):\n    return items\n",
            "tests/test_slow.py": "import time\n\ndef test_sleep():\n    time.sleep(30)\n"}
    o = Orchestrator(workspace_root=tmp_path / "ws")
    o.load_zip(make_zip(repo), "slow.zip", trusted=True)
    monkeypatch.setattr(config, "TEST_TIMEOUT_S", 2)
    o.analyze()                                     # baseline also times out, recorded as Blocked
    assert o.ctx.baseline.status is V.BLOCKED
    o.select_finding(o.ctx.findings[0].id)
    p = o.ctx.current_proposal
    o.approve(p.patch_id, p.patch_hash)
    assert o.ctx.latest_validation.status is V.BLOCKED and o.ctx.state is S.BLOCKED
    assert "timed out" in o.ctx.blocked_reason


def test_runner_counts_real_results(tmp_path):
    wc = tmp_path / "wc"
    (wc / "tests").mkdir(parents=True)
    (wc / "tests/test_x.py").write_text(
        "import pytest\n\ndef test_ok():\n    assert 1\n\ndef test_bad():\n    assert 0\n\n"
        "@pytest.mark.skip\ndef test_skip():\n    pass\n")
    out = sandbox_runner.run_pytest(wc)
    assert (out.passed, out.failed, out.skipped, out.errors) == (1, 1, 1, 0)
    assert out.exit_code == 1


def test_runner_env_is_stripped(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "leak-me")
    wc = tmp_path / "wc"
    (wc / "tests").mkdir(parents=True)
    (wc / "tests/test_env.py").write_text(
        "import os\n\ndef test_env():\n    assert 'SUPER_SECRET_TOKEN' not in os.environ\n")
    out = sandbox_runner.run_pytest(wc)
    assert (out.passed, out.failed) == (1, 0)


def test_baseline_links_windows_style_traceback_paths(tmp_path, monkeypatch):
    """Regression: pytest on Windows prints backslash paths; the finding must still be Confirmed."""
    real = sandbox_runner.run_pytest

    def windows_paths(workdir, timeout=None):
        out = real(workdir, timeout)
        out.cases = [replace(c, message=c.message.replace("/", "\\")) for c in out.cases]
        return out

    monkeypatch.setattr(sandbox_runner, "run_pytest", windows_paths)
    o = Orchestrator(workspace_root=tmp_path / "ws")
    o.load_sample()
    o.analyze()
    f = o.ctx.finding(fid(o, "R001"))
    assert f.confidence.value == "Confirmed"
    assert f.extra["confirmed_by"]
