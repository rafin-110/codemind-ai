"""Per-run workspace: read-only original snapshot plus fresh working copies."""

from __future__ import annotations

import os
import shutil
import stat
import sys
import uuid
from pathlib import Path

from codemind.models import RepoSnapshot


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def safe_join(root: Path, rel_path: str) -> Path:
    """Join and verify the result stays inside `root` (raises ValueError otherwise)."""
    root_resolved = root.resolve()
    target = (root_resolved / rel_path).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ValueError(f"path '{rel_path}' escapes workspace")
    return target


def make_read_only(root: Path) -> None:
    for p in root.rglob("*"):
        if p.is_file():
            p.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def make_working_copy(snapshot: RepoSnapshot, label: str) -> Path:
    """Copy the analysable files of the original into a new writable directory."""
    dest = snapshot.root.parent / f"working_copy_{label}"
    if dest.exists():
        remove_tree(dest)
    dest.mkdir(parents=True)
    for f in snapshot.included_files:
        src = safe_join(snapshot.root, f.rel_path)
        out = safe_join(dest, f.rel_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, out)          # copyfile: content only, new file is writable
    return dest


def remove_tree(path: Path) -> None:
    def _retry(func, p, _exc):
        os.chmod(p, stat.S_IWUSR | stat.S_IRUSR)
        func(p)

    if not path.exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry)
    else:  # pragma: no cover - older Pythons
        shutil.rmtree(path, onerror=_retry)
