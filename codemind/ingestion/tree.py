"""Render a directory tree for display."""

from __future__ import annotations

from codemind.models import FileInfo


def build_tree_text(files: list[FileInfo], root_name: str = ".") -> str:
    tree: dict = {}
    notes: dict[str, str] = {}
    for f in sorted(files, key=lambda f: f.rel_path):
        node = tree
        parts = f.rel_path.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part + "/", {})
        node[parts[-1]] = None
        if f.skipped_reason:
            notes[f.rel_path] = f.skipped_reason

    lines = [root_name]

    def walk(node: dict, prefix: str, path: str) -> None:
        entries = sorted(node.items(), key=lambda kv: (kv[1] is None, kv[0].lower()))
        for i, (name, child) in enumerate(entries):
            last = i == len(entries) - 1
            full = path + name
            note = f"   [skipped: {notes[full]}]" if full in notes else ""
            lines.append(f"{prefix}{'└── ' if last else '├── '}{name}{note}")
            if child is not None:
                walk(child, prefix + ("    " if last else "│   "), full)

    walk(tree, "", "")
    return "\n".join(lines)
