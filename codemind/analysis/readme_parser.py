"""Lightweight Markdown README parsing (headings, purpose paragraph, bullet features)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


@dataclass
class ReadmeInfo:
    path: str
    title: str = ""
    title_line: int = 0
    purpose: str = ""
    purpose_line: int = 0
    sections: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    has_install: bool = False
    has_usage: bool = False
    has_tests: bool = False
    text: str = ""


def find_readme(paths: list[str]) -> str | None:
    candidates = [p for p in paths if p.split("/")[-1].lower() in ("readme.md", "readme.rst", "readme.txt", "readme")]
    return min(candidates, key=lambda p: (p.count("/"), p)) if candidates else None


def parse_readme(path: str, text: str) -> ReadmeInfo:
    info = ReadmeInfo(path=path, text=text)
    lines = text.splitlines()
    in_code = False
    current = ""
    para: list[str] = []
    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = _HEADING.match(line)
        if m:
            heading = m.group(2).strip()
            if len(m.group(1)) == 1 and not info.title:
                info.title, info.title_line = heading, i
            else:
                info.sections.append(heading)
            current = heading.lower()
            low = current
            info.has_install |= any(k in low for k in ("install", "setup", "getting started"))
            info.has_usage |= any(k in low for k in ("usage", "run", "how to", "quick start", "quickstart"))
            info.has_tests |= "test" in low
            continue
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")) and "feature" in current:
            info.features.append(stripped[2:].strip())
        if not info.purpose:
            if stripped and not stripped.startswith((">", "- ", "* ", "|", "!", "<")):
                if not para:
                    info.purpose_line = i
                para.append(stripped)
            elif para:
                info.purpose = " ".join(para)
    if not info.purpose and para:
        info.purpose = " ".join(para)
    return info
