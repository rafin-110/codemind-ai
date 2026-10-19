"""Unified diff generation."""

from __future__ import annotations

import difflib


def unified_diff(rel_path: str, before: str, after: str, context: int = 3) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}", n=context))


def changed_line_count(diff: str) -> int:
    return sum(1 for line in diff.splitlines()
               if (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---")))
