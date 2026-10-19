"""Safe ZIP inspection and extraction. Uploaded code is never executed here.

Every entry is validated before anything is written; entries are then written one
by one (never `extractall`). See SECURITY_PLAN.md for the limits.
"""

from __future__ import annotations

import io
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from codemind import config
from codemind.ingestion import file_filter
from codemind.ingestion.tree import build_tree_text
from codemind.models import FileInfo, RepoSnapshot, sha256_bytes, sha256_text
from codemind.workspace import make_read_only, remove_tree, safe_join

_DRIVE = re.compile(r"^[A-Za-z]:")


class UnsafeArchiveError(ValueError):
    """The archive was rejected; nothing from it is kept."""


@dataclass(frozen=True)
class _Entry:
    info: zipfile.ZipInfo
    rel_path: str


def _validate_name(name: str) -> str:
    if "\x00" in name:
        raise UnsafeArchiveError(f"entry name contains a NUL byte: {name!r}")
    if "\\" in name:
        raise UnsafeArchiveError(f"entry '{name}' uses backslashes (possible path trick)")
    if name.startswith("/") or _DRIVE.match(name):
        raise UnsafeArchiveError(f"entry '{name}' is an absolute path")
    parts = PurePosixPath(name).parts
    if any(p == ".." for p in parts):
        raise UnsafeArchiveError(f"entry '{name}' escapes the workspace (path traversal)")
    return "/".join(p for p in parts if p not in ("", "."))


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def inspect_zip(data: bytes) -> list[_Entry]:
    """Validate the whole archive without writing anything. Raises UnsafeArchiveError."""
    if len(data) > config.MAX_ZIP_BYTES:
        raise UnsafeArchiveError(
            f"archive is {len(data) / 1e6:.1f} MB; limit is {config.MAX_ZIP_BYTES / 1e6:.0f} MB")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsafeArchiveError(f"not a valid ZIP file ({exc})") from exc

    infos = zf.infolist()
    if len(infos) > config.MAX_FILES:
        raise UnsafeArchiveError(f"archive has {len(infos)} entries; limit is {config.MAX_FILES}")

    total = 0
    entries: list[_Entry] = []
    for info in infos:
        rel = _validate_name(info.filename)
        if _is_symlink(info):
            raise UnsafeArchiveError(f"entry '{info.filename}' is a symbolic link")
        if info.flag_bits & 0x1:
            raise UnsafeArchiveError(f"entry '{info.filename}' is encrypted")
        if info.is_dir() or not rel:
            continue
        total += info.file_size
        if total > config.MAX_UNCOMPRESSED_BYTES:
            raise UnsafeArchiveError(
                f"uncompressed size exceeds {config.MAX_UNCOMPRESSED_BYTES / 1e6:.0f} MB")
        if info.compress_size and info.file_size > 1024 * 1024:
            ratio = info.file_size / info.compress_size
            if ratio > config.MAX_COMPRESSION_RATIO:
                raise UnsafeArchiveError(
                    f"entry '{info.filename}' has compression ratio {ratio:.0f}:1 (possible zip bomb)")
        entries.append(_Entry(info, rel))

    if not entries:
        raise UnsafeArchiveError("archive contains no files")
    return _strip_common_root(entries)


def _strip_common_root(entries: list[_Entry]) -> list[_Entry]:
    """GitHub-style archives wrap everything in one folder; remove it."""
    firsts = {e.rel_path.split("/", 1)[0] for e in entries}
    if len(firsts) == 1 and all("/" in e.rel_path for e in entries):
        return [_Entry(e.info, e.rel_path.split("/", 1)[1]) for e in entries]
    return entries


def _read_limited(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    # never trust the header size: read at most the declared size + 1 byte
    with zf.open(info) as fh:
        data = fh.read(info.file_size + 1)
    if len(data) != info.file_size:
        raise UnsafeArchiveError(f"entry '{info.filename}' size does not match its header")
    return data


def ingest_zip(data: bytes, run_dir: Path, *, source: str = "zip", display_name: str = "upload.zip",
               trusted: bool = False) -> RepoSnapshot:
    """Validate, filter and extract an archive into `run_dir/original` (made read-only)."""
    entries = inspect_zip(data)
    original = run_dir / "original"
    if original.exists():
        remove_tree(original)
    original.mkdir(parents=True)

    files: list[FileInfo] = []
    warnings: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for e in entries:
                reason = file_filter.skip_reason_by_path(e.rel_path, e.info.file_size)
                lang = file_filter.language_for(e.rel_path)
                if reason:
                    files.append(FileInfo(e.rel_path, e.info.file_size, lang, None, reason))
                    continue
                content = _read_limited(zf, e.info)
                reason = file_filter.skip_reason_by_content(content[:8192])
                if reason:
                    files.append(FileInfo(e.rel_path, e.info.file_size, lang, None, reason))
                    continue
                try:
                    target = safe_join(original, e.rel_path)
                except ValueError as exc:
                    raise UnsafeArchiveError(str(exc)) from exc
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                files.append(FileInfo(e.rel_path, len(content), lang, sha256_bytes(content)))
    except BaseException:
        remove_tree(original)
        raise

    included = [f for f in files if f.skipped_reason is None]
    if not included:
        warnings.append("no analysable text files after filtering")
    make_read_only(original)
    snap_hash = sha256_text("\n".join(f"{f.rel_path}:{f.sha256}" for f in sorted(included, key=lambda f: f.rel_path)))
    return RepoSnapshot(
        snapshot_id=run_dir.name,
        source=source,
        root=original,
        files=files,
        tree_text=build_tree_text(files, display_name.removesuffix(".zip")),
        snapshot_hash=snap_hash,
        display_name=display_name,
        ingest_warnings=warnings,
        trusted=trusted,
    )


def rehash_snapshot(snapshot: RepoSnapshot) -> str:
    """Recompute the snapshot hash from disk (used to prove the original is unchanged)."""
    parts = []
    for f in sorted(snapshot.included_files, key=lambda f: f.rel_path):
        p = safe_join(snapshot.root, f.rel_path)
        digest = sha256_bytes(p.read_bytes()) if p.exists() else "MISSING"
        parts.append(f"{f.rel_path}:{digest}")
    return sha256_text("\n".join(parts))


def zip_directory(src: Path) -> bytes:
    """Build an in-memory ZIP of a local directory (used for the bundled sample)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts:
                zf.write(p, p.relative_to(src).as_posix())
    return buf.getvalue()
