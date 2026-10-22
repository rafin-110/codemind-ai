"""Regression tests: pytest installed in the interpreter's user site-packages must still be found by the
isolated (-I) test process, and every kind of run must be reported honestly."""

import json
import os
import subprocess
import sys
from pathlib import Path

from codemind import models
from codemind.validation import sandbox_runner as sr

TINY_REPO = {
    "app.py": "def add(a, b):\n    return a + b\n",
    "tests/test_app.py": ("from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n\n\n"
                          "def test_broken():\n    assert add(1, 1) == 3\n"),
}


def _write_repo(root: Path, files: dict[str, str]) -> Path:
    work = root / "working_copy"
    for rel, text in files.items():
        p = work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return work


def test_isolated_child_can_import_pytest_even_when_it_cannot_see_site_packages():
    """Simulates pytest living only in a directory that `python -I` does not search (user site-packages)."""
    dirs = sr._pytest_search_dirs()
    assert dirs and any((Path(d) / "pytest").exists() for d in dirs)
    code = ("import sys\nsys.path[:] = [p for p in sys.path if 'packages' not in p]\n"
            "sys.argv = ['-c', sys.argv[1], '--version']\n" + sr._BOOTSTRAP)
    run = lambda d: subprocess.run([sys.executable, "-I", "-c", code, json.dumps(d)],  # noqa: E731
                                   capture_output=True, text=True)
    blind = run([])
    assert blind.returncode != 0 and "No module named" in blind.stderr          # the old failure mode
    sighted = run(dirs)
    assert sighted.returncode == 0 and "pytest" in (sighted.stdout + sighted.stderr).lower()


def test_run_pytest_command_uses_bootstrap_not_dash_m_and_keeps_isolation(tmp_path, monkeypatch):
    work = _write_repo(tmp_path, TINY_REPO)
    seen = {}
    real_popen = subprocess.Popen

    def spy(cmd, *a, **kw):
        if "pytest" in " ".join(map(str, cmd)) or "-c" in cmd:
            seen["cmd"], seen["env"] = list(cmd), dict(kw.get("env") or {})
        return real_popen(cmd, *a, **kw)

    monkeypatch.setenv("CODEMIND_TEST_SECRET_TOKEN", "do-not-leak")
    monkeypatch.setattr(sr.subprocess, "Popen", spy)
    sr.run_pytest(work, timeout=120)
    cmd = seen["cmd"]
    assert "-I" in cmd and "-B" in cmd                       # isolation preserved
    assert "-m" not in cmd and sr._BOOTSTRAP in cmd          # the old `-m pytest` launch is gone
    assert json.loads(cmd[cmd.index(sr._BOOTSTRAP) + 1]) == sr._pytest_search_dirs()
    assert "CODEMIND_TEST_SECRET_TOKEN" not in seen["env"]   # secrets still stripped


def test_run_pytest_reports_real_results_end_to_end(tmp_path):
    out = sr.run_pytest(_write_repo(tmp_path, TINY_REPO), timeout=120)
    assert out.ran and (out.passed, out.failed, out.errors) == (1, 1, 0)
    assert out.category == "tests_failed" and "No module named" not in out.output_tail


def test_timeout_is_still_reported_as_timeout(tmp_path):
    work = _write_repo(tmp_path, {"tests/test_slow.py": "import time\n\n\ndef test_slow():\n    time.sleep(30)\n"})
    out = sr.run_pytest(work, timeout=3)
    assert out.timed_out and not out.ran and out.category == "timeout" and out.total == 0


def test_crash_is_not_a_test_result(tmp_path):
    work = _write_repo(tmp_path, {"conftest.py": "raise RuntimeError('boom')\n",
                                  "tests/test_a.py": "def test_a():\n    assert True\n"})
    out = sr.run_pytest(work, timeout=60)
    assert not out.ran and out.category == "crash" and out.total == 0 and "boom" in out.output_tail


def test_missing_pytest_gets_its_own_explanation(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "pytest_available", lambda: False)
    out = sr.run_pytest(tmp_path)
    assert out.category == "missing_dependency" and not out.ran
    assert sys.executable in out.note and "pip install" in out.note


def test_output_text_cannot_fake_a_missing_package():
    """Tests that ran and failed are failures even if their output contains the phrase."""
    outcome = sr.RunOutcome(ran=True, exit_code=1, timed_out=False, failed=1,
                            cases=[models.TestCaseResult("t::x", "failed", "assert 'No module named pytest' in text")])
    sr._classify(outcome, "E assert 'No module named pytest' in text", 1)
    assert outcome.category == "tests_failed" and outcome.ran
    missing = sr.RunOutcome(ran=True, exit_code=1, timed_out=False)
    sr._classify(missing, "Traceback\nModuleNotFoundError: No module named 'pytest'", 1)
    assert missing.category == "missing_dependency" and not missing.ran
    crash = sr.RunOutcome(ran=True, exit_code=3, timed_out=False)
    sr._classify(crash, "INTERNALERROR> boom", 3)
    assert crash.category == "crash"
    none = sr.RunOutcome(ran=True, exit_code=5, timed_out=False)
    sr._classify(none, "no tests ran", 5)
    assert none.category == "no_tests" and none.ran
