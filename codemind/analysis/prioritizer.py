"""Order findings so the most severe, most certain issues come first."""

from __future__ import annotations

from codemind.models import Finding


def prioritize(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (-f.severity.rank, -f.confidence.rank, f.file, f.line))


def renumber(findings: list[Finding]) -> list[Finding]:
    for i, f in enumerate(findings, start=1):
        f.id = f"F-{i:03d}"
    return findings


def severity_counts(findings: list[Finding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
    return counts
