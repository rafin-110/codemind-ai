"""Decide which archive entries are analysed, skipped, or treated as sensitive."""

from __future__ import annotations

import fnmatch
import re
from pathlib import PurePosixPath

from codemind import config


def language_for(rel_path: str) -> str:
    suffix = PurePosixPath(rel_path).suffix.lower()
    if PurePosixPath(rel_path).name.lower() in {"dockerfile", "makefile"}:
        return PurePosixPath(rel_path).name
    return config.LANGUAGE_BY_EXT.get(suffix, "Other")


def is_sensitive_name(rel_path: str) -> bool:
    name = PurePosixPath(rel_path).name.lower()
    return any(fnmatch.fnmatch(name, pat) for pat in config.SENSITIVE_NAME_PATTERNS)


def ignored_dir(rel_path: str) -> str | None:
    for part in PurePosixPath(rel_path).parts[:-1]:
        if part in config.IGNORED_DIRS or part.endswith(".egg-info"):
            return part
    return None


GENERATED_RUN_COPY = "generated CodeMind run copy (not source)"

# CodeMind's own run layout: <workspace>/<12-hex run id>/original/... and working_copy_<label>[...]
# (plus working_copy_<label>_home/ and working_copy_<label>_junit.xml). Uploading a project that
# contains old runs would otherwise analyse every copy as if it were source code. Only this exact
# layout is matched, so a real `workspace/` package in a user's project is still analysed.
_RUN_COPY = re.compile(
    rf"(?:^|/){re.escape(config.DEFAULT_WORKSPACE.name)}/[0-9a-f]{{12}}/(?:original|working_copy_[^/]+)(?:/|$)")


def generated_run_copy(rel_path: str) -> bool:
    return _RUN_COPY.search(rel_path) is not None


def looks_binary(head: bytes) -> bool:
    if b"\x00" in head:
        return True
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as exc:
        # a multi-byte char cut at the 8 KB boundary is fine
        return exc.start < len(head) - 4
    return False


def skip_reason_by_path(rel_path: str, size: int) -> str | None:
    """Reasons that can be decided without reading content (content is never read for these)."""
    d = ignored_dir(rel_path)
    if d:
        return f"ignored directory '{d}'"
    if generated_run_copy(rel_path):
        return GENERATED_RUN_COPY
    if is_sensitive_name(rel_path):
        return "sensitive file (content not read)"
    if size > config.MAX_FILE_BYTES:
        return f"file larger than {config.MAX_FILE_BYTES // 1024} KB"
    return None


def skip_reason_by_content(head: bytes) -> str | None:
    if looks_binary(head):
        return "binary file"
    return None
