"""CodeMind's own run folders (workspace/<run id>/original, working_copy_*) are not source code.

Uploading a project that contains earlier runs must not report every copied file again,
while real code in a user's `workspace/` folder and genuinely separate files are still analysed.
"""

import pytest

from codemind.ingestion import file_filter
from codemind.ingestion.zip_loader import ingest_zip
from codemind.models import Severity
from codemind.orchestrator.orchestrator import Orchestrator
from tests.helpers import make_zip

EVAL = "def read_scores():\n    raw = input('scores: ')\n    return eval(raw)\n"   # Critical: user input reaches eval
RUN = "workspace/3fec7444a8d5"


@pytest.mark.parametrize("path", [
    f"{RUN}/original/grades/cli.py",
    f"{RUN}/working_copy_baseline/grades/cli.py",
    f"{RUN}/working_copy_P-001-1-abc123/grades/cli.py",
    f"{RUN}/working_copy_baseline_home/.cache/x.py",
    f"{RUN}/working_copy_baseline_junit.xml",
    f"project/{RUN}/original/grades/cli.py",                    # nested inside another folder
    f"{RUN}/original/codemind-ai/workspace/f6f38509bf70/working_copy_baseline/a.py",
])
def test_generated_run_copies_are_recognised(path):
    assert file_filter.skip_reason_by_path(path, 10) == file_filter.GENERATED_RUN_COPY


@pytest.mark.parametrize("path", [
    "workspace/utils.py",                                       # a real package called workspace
    "workspace/original/cli.py",                                # no run id
    "workspace/3fec7444a8d5/cli.py",                            # run-id-like name but not a copy folder
    "workspace/3FEC7444A8D5/original/cli.py",                   # run ids are lowercase hex
    "workspace/3fec7444a8d5x/original/cli.py",                  # not exactly 12 characters
    "workspace/3fec7444a8d5/originals/cli.py",
    "myworkspace/3fec7444a8d5/original/cli.py",
    "src/original/working_copy_notes.py",
])
def test_ordinary_paths_are_not_treated_as_run_copies(path):
    assert file_filter.skip_reason_by_path(path, 10) is None


def test_ingest_lists_run_copies_as_skipped_with_a_warning(tmp_path):
    snap = ingest_zip(make_zip({
        "app/cli.py": EVAL,
        f"{RUN}/original/app/cli.py": EVAL,
        f"{RUN}/working_copy_baseline/app/cli.py": EVAL,
        f"{RUN}/working_copy_baseline_junit.xml": "<testsuite/>",
    }), tmp_path / "run")
    assert [f.rel_path for f in snap.included_files] == ["app/cli.py"]
    skipped = {f.rel_path: f.skipped_reason for f in snap.files if f.skipped_reason}
    assert len(skipped) == 3 and set(skipped.values()) == {file_filter.GENERATED_RUN_COPY}
    assert any("skipped 3 file(s) in CodeMind run folders" in w for w in snap.ingest_warnings)
    assert not (snap.root / RUN).exists()                       # never extracted


def test_no_warning_without_run_copies(tmp_path):
    snap = ingest_zip(make_zip({"app/cli.py": EVAL}), tmp_path / "run")
    assert not any("run folders" in w for w in snap.ingest_warnings)


def _critical_eval_files(tmp_path, entries):
    o = Orchestrator(workspace_root=tmp_path)
    o.load_zip(make_zip(entries), "project.zip")
    o.analyze()
    return sorted(f.file for f in o.ctx.findings if f.rule_id == "R003" and f.severity is Severity.CRITICAL)


def test_run_copies_do_not_multiply_findings(tmp_path):
    files = _critical_eval_files(tmp_path, {
        "README.md": "# Project\n",
        "grades/cli.py": EVAL,
        f"{RUN}/original/grades/cli.py": EVAL,
        f"{RUN}/working_copy_baseline/grades/cli.py": EVAL,
        "workspace/f6f38509bf70/original/grades/cli.py": EVAL,
        "workspace/f6f38509bf70/working_copy_baseline/grades/cli.py": EVAL,
    })
    assert files == ["grades/cli.py"]


def test_same_vulnerability_in_different_real_files_is_still_reported(tmp_path):
    files = _critical_eval_files(tmp_path, {
        "README.md": "# Project\n",
        "grades/cli.py": EVAL,
        "admin/cli.py": EVAL,                                   # identical code, different file
        "workspace/tools.py": EVAL,                             # real code in a folder named workspace
    })
    assert files == ["admin/cli.py", "grades/cli.py", "workspace/tools.py"]
