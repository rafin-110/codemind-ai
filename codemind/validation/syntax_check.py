"""Syntax check with compile(): parses and byte-compiles without executing anything."""

from __future__ import annotations

import time
from pathlib import Path

from codemind.models import CheckResult, ValidationStatus


def check_files(root: Path, rel_paths: list[str]) -> CheckResult:
    start = time.perf_counter()
    errors = []
    for rel in rel_paths:
        if not rel.endswith(".py"):
            continue
        src = (root / rel).read_text(encoding="utf-8")
        try:
            compile(src, rel, "exec", dont_inherit=True)
        except SyntaxError as exc:
            errors.append(f"{rel}:{exc.lineno}: {exc.msg}")
    status = ValidationStatus.FAILED if errors else ValidationStatus.PASSED
    detail = "; ".join(errors) if errors else f"{len(rel_paths)} file(s) compile (no code executed)"
    return CheckResult("Syntax check", status, detail, time.perf_counter() - start)
