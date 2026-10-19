"""Dependency metadata (requirements.txt, pyproject.toml). Nothing is executed or installed."""

from __future__ import annotations

import re
import tomllib

_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")

KNOWN_TECH = {
    "streamlit": "Streamlit", "flask": "Flask", "django": "Django", "fastapi": "FastAPI",
    "pandas": "pandas", "numpy": "NumPy", "sklearn": "scikit-learn", "scikit-learn": "scikit-learn",
    "torch": "PyTorch", "tensorflow": "TensorFlow", "requests": "requests", "pytest": "pytest",
    "sqlite3": "SQLite", "sqlalchemy": "SQLAlchemy", "matplotlib": "Matplotlib",
    "langchain": "LangChain", "openai": "OpenAI SDK", "tkinter": "Tkinter",
}


def parse_requirements(text: str) -> list[tuple[str, int]]:
    out = []
    for i, line in enumerate(text.splitlines(), start=1):
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = _REQ_NAME.match(line)
        if m:
            out.append((m.group(1), i))
    return out


def parse_pyproject(text: str) -> list[str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    deps = list(data.get("project", {}).get("dependencies", []))
    poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    deps += [k for k in poetry if k.lower() != "python"]
    names = []
    for d in deps:
        m = _REQ_NAME.match(d)
        if m:
            names.append(m.group(1))
    return names


def detect_technologies(languages: set[str], dependencies: list[str], imports: set[str]) -> list[str]:
    tech = set(lang for lang in languages if lang not in ("Other", "Text", "Markdown"))
    for name in list(dependencies) + list(imports):
        key = name.lower().split(".")[0]
        if key in KNOWN_TECH:
            tech.add(KNOWN_TECH[key])
    return sorted(tech)
