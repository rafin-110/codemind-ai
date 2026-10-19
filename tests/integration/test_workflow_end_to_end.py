"""T-E2E-01 and orchestrator edge cases, driven exactly like the UI drives them."""

import json

import pytest

from codemind.models import ValidationStatus as V, WorkflowState as S
from codemind.orchestrator.orchestrator import Orchestrator, WorkflowError
from codemind.validation.report import build_json, build_markdown
from tests.helpers import make_zip


def test_full_demo_flow(tmp_path):
    o = Orchestrator(workspace_root=tmp_path)
    o.load_sample()
    assert o.ctx.state is S.PLANNED and o.ctx.plan.step_status["baseline"] == "pending"
    o.analyze()
    c = o.ctx
    assert c.state is S.FINDINGS_READY and len(c.findings) == 9
    assert c.baseline.tests_failed == 1                      # the original really fails one test
    agents = [e.agent for e in c.log]
    order = [a for a in dict.fromkeys(agents)]
    assert order.index("Repository Understanding Agent") < order.index("Bug & Risk Analysis Agent") \
        < order.index("Solution & Architecture Advisor")

    by_rule = {f.rule_id: f.id for f in c.findings}
    # 1) reject one proposal
    o.select_finding(by_rule["R002"])
    p = c.current_proposal
    o.reject(p.patch_id, p.patch_hash)
    # 2) approve a different one; first strategy fails real tests, retry, approve again
    o.select_finding(by_rule["R001"])
    o.approve(c.current_proposal.patch_id, c.current_proposal.patch_hash)
    assert c.validations[-1].status is V.FAILED and c.state is S.AWAITING_APPROVAL
    o.approve(c.current_proposal.patch_id, c.current_proposal.patch_hash)
    assert c.state is S.VALIDATED
    assert c.finding(by_rule["R001"]).verification is V.PASSED

    events = [d.event for d in c.decisions]
    assert events == ["plan_created", "analysis_started", "analysis_complete",
                      "finding_selected", "critic_approved", "human_rejected",
                      "finding_selected", "critic_approved", "human_approved", "validation_started",
                      "validation_failed", "retry_proposed", "critic_approved",
                      "human_approved", "validation_started", "validation_passed"]

    report = json.loads(build_json(c))
    assert report["original_unchanged_at_report_time"] is True
    assert report["state"] == "VALIDATED"
    assert [a["decision"] for a in report["approvals"]] == ["rejected", "approved", "approved"]
    md = build_markdown(c)
    assert "Original files unchanged: **yes**" in md and "```diff" in md
    assert "4f9a2b7c1d8e3f60" not in md and "4f9a2b7c1d8e3f60" not in json.dumps(report)

    # 3) another finding can be worked on after a finished cycle
    o.select_finding(by_rule["R009"])
    assert c.state is S.AWAITING_APPROVAL


def test_rejected_archive_blocks_with_reason(tmp_path):
    o = Orchestrator(workspace_root=tmp_path)
    o.load_zip(make_zip({"../evil.py": "x"}), "evil.zip")
    assert o.ctx.state is S.BLOCKED and "path traversal" in o.ctx.blocked_reason
    with pytest.raises(WorkflowError):
        o.analyze()
    with pytest.raises(WorkflowError):
        o.back_to_findings()


def test_docs_only_repo_is_structure_only(tmp_path):
    o = Orchestrator(workspace_root=tmp_path)
    o.load_zip(make_zip({"README.md": "# Notes\n\nJust notes.\n", "notes/todo.md": "- a\n"}), "docs.zip")
    o.analyze()
    c = o.ctx
    assert c.state is S.FINDINGS_READY and c.findings == [] and c.analysis_status is V.NOT_RUN
    assert c.plan.step_status["analyze"] == "skipped" and c.summary.title == "Notes"


def test_analyze_twice_is_refused(tmp_path):
    o = Orchestrator(workspace_root=tmp_path)
    o.load_sample()
    o.analyze()
    with pytest.raises(WorkflowError):
        o.analyze()


def test_unexpected_error_fails_safe(tmp_path, monkeypatch):
    o = Orchestrator(workspace_root=tmp_path)
    o.load_sample()
    monkeypatch.setattr(o.bug_agent, "run", lambda ctx, **kw: (_ for _ in ()).throw(RuntimeError("rule engine crashed")))
    o.analyze()
    assert o.ctx.state is S.BLOCKED and "rule engine crashed" in o.ctx.blocked_reason
    assert o.ctx.log[-2].error.startswith("RuntimeError")
