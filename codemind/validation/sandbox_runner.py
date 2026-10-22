"""Run a repository's pytest suite in a separate, constrained process.

This is NOT a security sandbox. It is a subprocess with: a timeout (process group
killed), a stripped environment, `-I` isolated mode, no bytecode/cache writes, POSIX
resource limits when available, and no network when `unshare` works on Linux.
Uploaded dependencies are never installed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from codemind import config
from codemind.models import TestCaseResult

try:
    import resource  # POSIX only
except ImportError:  # pragma: no cover - Windows
    resource = None

_NET_ISOLATION: bool | None = None


@dataclass
class RunOutcome:
    ran: bool
    exit_code: int | None
    timed_out: bool
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    cases: list[TestCaseResult] = field(default_factory=list)
    output_tail: str = ""
    isolation_level: str = ""
    limitations: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    note: str = ""
    # why the run ended: ok | tests_failed | collection_error | no_tests | missing_dependency |
    #                    timeout | crash | no_results
    category: str = ""

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped


def network_isolation_available() -> bool:
    global _NET_ISOLATION
    if _NET_ISOLATION is None:
        _NET_ISOLATION = False
        if sys.platform.startswith("linux") and shutil.which("unshare"):
            try:
                r = subprocess.run(["unshare", "--net", "--map-root-user", "true"], capture_output=True, timeout=5)
                _NET_ISOLATION = r.returncode == 0
            except (OSError, subprocess.SubprocessError):
                _NET_ISOLATION = False
    return _NET_ISOLATION


# Windows breaks in odd ways (stray "%SystemDrive%" folders, failed WMI/platform calls, missing
# PATHEXT) when the child process gets an almost empty environment. These system variables are
# passed through; everything else (tokens, API keys, user paths) is dropped.
_WINDOWS_PASSTHROUGH = (
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "PROGRAMDATA", "ALLUSERSPROFILE",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "COMMONPROGRAMFILES",
    "COMMONPROGRAMFILES(X86)", "COMMONPROGRAMW6432", "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "OS", "USERNAME", "USERDOMAIN", "COMPUTERNAME",
)


def _clean_env(workdir: Path, environ: dict[str, str] | None = None,
               windows: bool | None = None) -> dict[str, str]:
    """Minimal environment for the test process. `environ`/`windows` exist so tests can simulate Windows."""
    environ = os.environ if environ is None else environ
    windows = (os.name == "nt") if windows is None else windows
    home = workdir.parent / f"{workdir.name}_home"
    home.mkdir(exist_ok=True)
    env = {"PATH": environ.get("PATH", ""), "HOME": str(home), "TMPDIR": str(home),
           "TEMP": str(home), "TMP": str(home), "PYTHONHASHSEED": "0", "LANG": "C.UTF-8"}
    if windows:
        upper = {k.upper(): v for k, v in environ.items()}
        for key in _WINDOWS_PASSTHROUGH:
            if key in upper:
                env[key] = upper[key]
        env.setdefault("SYSTEMROOT", r"C:\Windows")
        env.setdefault("SYSTEMDRIVE", env["SYSTEMROOT"][:2])
        for key in ("USERPROFILE", "APPDATA", "LOCALAPPDATA"):   # user data dirs point at the sandbox home
            env[key] = str(home)
    return env


# The test process runs in isolated mode (-I), which ignores user site-packages and PYTHONPATH. When pytest was
# installed with `pip install --user` (typical for Microsoft Store Python or a non-admin install), the isolated
# child could not import it although the Streamlit process could. These directories, taken from the interpreter
# that runs CodeMind, are appended to the END of the child's sys.path: the repository can never shadow them.
_PYTEST_PACKAGES = ("pytest", "_pytest", "pluggy", "iniconfig", "packaging", "colorama", "exceptiongroup",
                    "tomli", "pygments")
_BOOTSTRAP = ("import json, sys\n"
              "sys.path.extend(json.loads(sys.argv[1]))\n"
              "import pytest\n"
              "sys.exit(pytest.main(sys.argv[2:]))\n")
_MISSING_MODULE = re.compile(r"No module named ['\"]?([\w.]+)")


def pytest_available() -> bool:
    try:
        return importlib.util.find_spec("pytest") is not None
    except (ImportError, ValueError):
        return False


def _pytest_search_dirs() -> list[str]:
    dirs: list[str] = []
    for name in _PYTEST_PACKAGES:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            continue
        if spec is None or not spec.origin or not os.path.exists(spec.origin):
            continue
        origin = Path(spec.origin).resolve()
        parent = str(origin.parent.parent if origin.name == "__init__.py" else origin.parent)
        if parent not in dirs:
            dirs.append(parent)
    return dirs


def _classify(outcome: RunOutcome, text: str, returncode: int) -> None:
    """Give every run exactly one honest category and a human explanation."""
    tail = "\n".join(text.splitlines()[-15:])
    if outcome.cases:
        collection = [c for c in outcome.cases if c.outcome == "error" and "collect" in c.message[:300].lower()]
        if outcome.failed:
            outcome.category = "tests_failed"
            outcome.note = f"{outcome.failed} test(s) failed"
        elif collection:
            outcome.category = "collection_error"
            outcome.note = f"{len(collection)} collection error(s): pytest could not import or collect test modules"
        elif outcome.errors:
            outcome.category = "tests_failed"
            outcome.note = f"{outcome.errors} test(s) raised errors in setup or teardown"
        else:
            outcome.category = "ok"
        return
    missing = _MISSING_MODULE.search(tail)
    if returncode == 5:
        outcome.category = "no_tests"
        outcome.note = "pytest ran but collected no tests (exit code 5)"
    elif missing and returncode != 0:
        outcome.ran = False
        outcome.category = "missing_dependency"
        outcome.note = (f"the test process could not import '{missing.group(1)}'. Interpreter used: {sys.executable}. "
                        f"Install the missing package for that interpreter, e.g. "
                        f"`{sys.executable} -m pip install -r requirements.txt`")
    elif returncode != 0:
        outcome.ran = False
        outcome.category = "crash"
        outcome.note = (f"pytest exited with code {returncode} before writing any test results "
                        "(crash or usage error); see the output below")
    else:
        outcome.ran = False
        outcome.category = "no_results"
        outcome.note = "pytest exited normally but wrote no results file"


def _parse_junit(xml_path: Path) -> list[TestCaseResult]:
    cases = []
    root = ET.parse(xml_path).getroot()
    for tc in root.iter("testcase"):
        name = f"{tc.get('classname', '')}::{tc.get('name', '')}".strip(":")
        outcome, message = "passed", ""
        for tag in ("failure", "error", "skipped"):
            el = tc.find(tag)
            if el is not None:
                outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
                message = ((el.get("message") or "") + "\n" + (el.text or "")).strip()[:2000]
                break
        cases.append(TestCaseResult(name, outcome, message))
    return cases


def run_pytest(workdir: Path, timeout: float | None = None) -> RunOutcome:
    timeout = timeout or config.TEST_TIMEOUT_S
    xml_path = workdir.parent / f"{workdir.name}_junit.xml"
    if xml_path.exists():
        xml_path.unlink()
    if not pytest_available():
        return RunOutcome(
            ran=False, exit_code=None, timed_out=False, category="missing_dependency",
            note=(f"pytest is not installed for the Python interpreter that runs CodeMind ({sys.executable}). "
                  f"Run: {sys.executable} -m pip install -r requirements.txt"))
    cmd = [sys.executable, "-I", "-B", "-c", _BOOTSTRAP, json.dumps(_pytest_search_dirs()), "-q", "-p",
           "no:cacheprovider", "--rootdir", str(workdir), "-o", "pythonpath=.", f"--junitxml={xml_path}"]
    isolation = ["separate process", f"{timeout:.0f}s timeout", "stripped environment", "isolated mode (-I)"]
    limitations = ["Not a security sandbox: the filesystem outside the working copy is not hidden."]
    if resource is not None:
        isolation.append("CPU/memory/file-size limits")
    else:
        limitations.append("Resource limits unavailable on this OS: only the timeout is enforced.")
    if network_isolation_available():
        cmd = ["unshare", "--net", "--map-root-user"] + cmd
        isolation.append("no network (unshare)")
    else:
        limitations.append("Network access is not blocked on this machine.")

    kwargs = {}
    if os.name == "posix":
        kwargs["start_new_session"] = True
        if resource is not None:
            kwargs["preexec_fn"] = _limits_posix
    else:  # pragma: no cover - Windows
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    start = time.perf_counter()
    proc = subprocess.Popen(cmd, cwd=workdir, env=_clean_env(workdir), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, shell=False, **kwargs)
    try:
        out, _ = proc.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        _kill(proc)
        try:
            out, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:   # a grandchild still holds the pipe open
            out = b""
        timed_out = True
    duration = time.perf_counter() - start
    text = out.decode("utf-8", errors="replace")
    outcome = RunOutcome(ran=not timed_out, exit_code=proc.returncode, timed_out=timed_out,
                         output_tail="\n".join(text.splitlines()[-60:]),
                         isolation_level=", ".join(isolation), limitations=limitations, duration_s=duration)
    if timed_out:
        outcome.category = "timeout"
        outcome.note = (f"timed out after {timeout:.0f}s; process group killed. Set the environment "
                        "variable CODEMIND_TEST_TIMEOUT (seconds) to allow a longer run.")
        return outcome
    if xml_path.exists():
        try:
            outcome.cases = _parse_junit(xml_path)
        except ET.ParseError:
            outcome.note = "could not parse JUnit XML"
    field_for = {"passed": "passed", "failed": "failed", "error": "errors", "skipped": "skipped"}
    for c in outcome.cases:
        setattr(outcome, field_for[c.outcome], getattr(outcome, field_for[c.outcome]) + 1)
    _classify(outcome, text, proc.returncode)
    return outcome


def _limits_posix() -> None:
    cpu = config.TEST_TIMEOUT_S + 5
    for lim, val in ((resource.RLIMIT_CPU, cpu), (resource.RLIMIT_AS, 1024 ** 3),
                     (resource.RLIMIT_FSIZE, 50 * 1024 ** 2), (resource.RLIMIT_NOFILE, 256)):
        try:
            soft, hard = resource.getrlimit(lim)
            new = val if hard == resource.RLIM_INFINITY else min(val, hard)
            resource.setrlimit(lim, (new, new if hard == resource.RLIM_INFINITY else hard))
        except (ValueError, OSError):
            pass


def _kill(proc: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:  # pragma: no cover - Windows: kill the whole process tree, not just pytest itself
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=15, check=False)
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError, subprocess.SubprocessError):
        try:
            proc.kill()
        except OSError:
            pass
