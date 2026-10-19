"""Run a repository's pytest suite in a separate, constrained process.

This is NOT a security sandbox. It is a subprocess with: a timeout (process group
killed), a stripped environment, `-I` isolated mode, no bytecode/cache writes, POSIX
resource limits when available, and no network when `unshare` works on Linux.
Uploaded dependencies are never installed.
"""

from __future__ import annotations

import os
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


def _clean_env(workdir: Path) -> dict[str, str]:
    home = workdir.parent / f"{workdir.name}_home"
    home.mkdir(exist_ok=True)
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home), "TMPDIR": str(home),
           "TEMP": str(home), "TMP": str(home), "PYTHONHASHSEED": "0", "LANG": "C.UTF-8"}
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    return env


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
    cmd = [sys.executable, "-I", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
           "--rootdir", str(workdir), "-o", "pythonpath=.", f"--junitxml={xml_path}"]
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
        out, _ = proc.communicate()
        timed_out = True
    duration = time.perf_counter() - start
    text = out.decode("utf-8", errors="replace")
    outcome = RunOutcome(ran=not timed_out, exit_code=proc.returncode, timed_out=timed_out,
                         output_tail="\n".join(text.splitlines()[-60:]),
                         isolation_level=", ".join(isolation), limitations=limitations, duration_s=duration)
    if timed_out:
        outcome.note = f"timed out after {timeout:.0f}s; process group killed"
        return outcome
    if "No module named pytest" in text:
        outcome.ran = False
        outcome.note = "pytest is not installed in this Python environment"
        return outcome
    if xml_path.exists():
        try:
            outcome.cases = _parse_junit(xml_path)
        except ET.ParseError:
            outcome.note = "could not parse JUnit XML"
    field_for = {"passed": "passed", "failed": "failed", "error": "errors", "skipped": "skipped"}
    for c in outcome.cases:
        setattr(outcome, field_for[c.outcome], getattr(outcome, field_for[c.outcome]) + 1)
    if proc.returncode == 5:
        outcome.note = "no tests were collected"
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
        else:  # pragma: no cover
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()
