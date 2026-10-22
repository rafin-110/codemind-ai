"""Regression tests for the Windows environment, ZIP separator handling and honest baseline reporting."""

import pytest

from codemind import config
from codemind.ingestion.zip_loader import UnsafeArchiveError, ingest_zip
from codemind.models import ValidationStatus as V
from codemind.orchestrator.orchestrator import Orchestrator
from codemind.validation import sandbox_runner
from tests.helpers import make_zip


# ------------------------------------------------------------------ environment

def test_windows_env_keeps_system_vars_and_drops_secrets(tmp_path):
    (tmp_path / "run").mkdir()
    environ = {"SystemRoot": r"C:\Windows", "SystemDrive": "C:", "ComSpec": r"C:\Windows\System32\cmd.exe",
               "PATHEXT": ".COM;.EXE", "PATH": r"C:\Python", "ProgramData": r"C:\ProgramData",
               "OPENAI_API_KEY": "secret", "GITHUB_TOKEN": "secret", "USERPROFILE": r"C:\Users\me"}
    env = sandbox_runner._clean_env(tmp_path / "run" / "wc", environ, windows=True)
    assert env["SYSTEMDRIVE"] == "C:" and env["SYSTEMROOT"] == r"C:\Windows"
    assert env["COMSPEC"].endswith("cmd.exe") and env["PATHEXT"] == ".COM;.EXE"
    assert env["PROGRAMDATA"] == r"C:\ProgramData"
    assert "OPENAI_API_KEY" not in env and "GITHUB_TOKEN" not in env
    home = str(tmp_path / "run" / "wc_home")
    assert env["USERPROFILE"] == home and env["APPDATA"] == home and env["LOCALAPPDATA"] == home


def test_windows_env_has_defaults_when_system_vars_missing(tmp_path):
    env = sandbox_runner._clean_env(tmp_path / "wc", {"PATH": "x"}, windows=True)
    assert env["SYSTEMROOT"] == r"C:\Windows" and env["SYSTEMDRIVE"] == "C:"


def test_posix_env_has_no_windows_vars(tmp_path):
    env = sandbox_runner._clean_env(tmp_path / "wc", {"PATH": "/bin", "SECRET": "x"}, windows=False)
    assert "SYSTEMDRIVE" not in env and "SECRET" not in env and env["PATH"] == "/bin"


def test_timeout_default_and_override():
    assert config.TEST_TIMEOUT_S >= 60       # env override CODEMIND_TEST_TIMEOUT is read at import


# ------------------------------------------------------------------ zip separators

def test_backslash_separators_are_normalised_not_trusted(tmp_path):
    data = make_zip({"app\\main.py": "x = 1\n", "app\\pkg\\util.py": "y = 2\n"})
    snap = ingest_zip(data, tmp_path / "run")
    # the shared "app/" wrapper folder is stripped, exactly as for forward-slash archives
    assert sorted(f.rel_path for f in snap.included_files) == ["main.py", "pkg/util.py"]


@pytest.mark.parametrize("bad", ["a\\..\\..\\evil.py", "\\evil.py", "C:\\evil.py", "ok\\file.py:stream",
                                 "dir\\..\\evil.py"])
def test_backslash_and_colon_tricks_still_rejected(tmp_path, bad):
    with pytest.raises(UnsafeArchiveError):
        ingest_zip(make_zip({"ok.py": "x = 1\n", bad: "print(1)\n"}), tmp_path / "run")


# ------------------------------------------------------------------ honest baseline

CRASHING_REPO = {
    "app.py": "def f():\n    return 1\n",
    "tests/test_app.py": "from app import f\n\n\ndef test_f():\n    assert f() == 1\n",
    "conftest.py": "raise RuntimeError('simulated broken test environment')\n",
}


def test_crashed_pytest_is_not_reported_as_pass(tmp_path):
    o = Orchestrator(workspace_root=tmp_path)
    o.load_zip(make_zip(CRASHING_REPO), "crash.zip", trusted=True)
    o.analyze()
    b = o.ctx.baseline
    assert b is not None
    assert b.status is V.NOT_RUN                                   # never PASSED with zero tests
    assert b.tests_passed == b.tests_failed == b.tests_errors == 0
    assert "exit code" in b.checks[0].detail and b.checks[0].status is V.NOT_RUN
    assert o.ctx.plan.step_status["baseline"] == "failed"          # step does not claim success
    assert "simulated broken test environment" in b.raw_output_tail


def test_good_baseline_marks_step_done(tmp_path):
    o = Orchestrator(workspace_root=tmp_path)
    o.load_sample()
    o.analyze()
    assert o.ctx.baseline.status is V.FAILED                       # the sample has one real failing test
    assert o.ctx.plan.step_status["baseline"] == "done"
    assert o.ctx.baseline.checks and "failed" in o.ctx.baseline.checks[0].detail
