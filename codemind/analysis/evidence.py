"""Evidence snippets with line numbers, and secret redaction for anything displayed."""

from __future__ import annotations

import re

from codemind.models import Evidence

# key-looking literals: sk-..., ghp_..., AKIA..., long hex/base64 tokens in quotes
_SECRET_LITERAL = re.compile(
    r"""(?P<q>['"])(?P<val>(?:sk-|ghp_|gho_|xox[bap]-|AKIA)[A-Za-z0-9_\-]{6,}|[A-Za-z0-9+/_\-]{24,})(?P=q)""")
_ASSIGN_SECRET = re.compile(
    r"""(?P<name>\b\w*(?:key|secret|token|passw(?:or)?d|pwd)\w*\b\s*[:=]\s*)(?P<q>['"])(?P<val>[^'"]{4,})(?P=q)""",
    re.IGNORECASE)


def _mask(value: str) -> str:
    return (value[:4] if len(value) > 8 else "") + "…[REDACTED]"


def redact(text: str) -> str:
    text = _ASSIGN_SECRET.sub(lambda m: f"{m.group('name')}{m.group('q')}{_mask(m.group('val'))}{m.group('q')}", text)
    return _SECRET_LITERAL.sub(lambda m: f"{m.group('q')}{_mask(m.group('val'))}{m.group('q')}", text)


def snippet(source: str, line_start: int, line_end: int | None = None, context: int = 1) -> str:
    lines = source.splitlines()
    line_end = line_end or line_start
    lo = max(1, line_start - context)
    hi = min(len(lines), line_end + context)
    width = len(str(hi))
    out = []
    for n in range(lo, hi + 1):
        marker = ">" if line_start <= n <= line_end else " "
        out.append(f"{marker} {str(n).rjust(width)} | {lines[n - 1]}")
    return redact("\n".join(out))


def make_evidence(file: str, source: str, line_start: int, line_end: int | None = None,
                  note: str = "", context: int = 1) -> Evidence:
    line_end = line_end or line_start
    return Evidence(file=file, line_start=line_start, line_end=line_end,
                    snippet=snippet(source, line_start, line_end, context), note=note)
