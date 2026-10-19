"""Apply an APPROVED patch to a fresh working copy. The original is never opened for writing."""

from __future__ import annotations

from pathlib import Path

from codemind.models import PatchProposal, WorkflowContext, sha256_bytes
from codemind.patching.approval import ApprovalError, valid_approval
from codemind.workspace import make_working_copy, safe_join


class PatchScopeError(ValueError):
    """The patch tries to touch something outside its approved scope."""


def apply_to_copy(ctx: WorkflowContext, proposal: PatchProposal) -> Path:
    if valid_approval(ctx, proposal) is None:
        raise ApprovalError("no valid approval for this exact patch")
    snap = ctx.snapshot
    known = {f.rel_path: f for f in snap.included_files}
    for e in proposal.edits:
        if e.rel_path not in proposal.affected_files:
            raise PatchScopeError(f"edit to '{e.rel_path}' is outside the approved files")
        if e.rel_path not in known:
            raise PatchScopeError(f"'{e.rel_path}' is not an existing analysed file (new files are not allowed)")
        safe_join(snap.root, e.rel_path)          # raises on traversal
        if known[e.rel_path].sha256 != e.original_sha256:
            raise PatchScopeError(f"'{e.rel_path}' does not match the version the patch was built from")

    copy_root = make_working_copy(snap, proposal.patch_id)
    if snap.root.resolve() in copy_root.resolve().parents or copy_root.resolve() == snap.root.resolve():
        raise PatchScopeError("working copy must not be inside the original")
    for e in proposal.edits:
        target = safe_join(copy_root, e.rel_path)
        if sha256_bytes(target.read_bytes()) != e.original_sha256:
            raise PatchScopeError(f"working copy of '{e.rel_path}' differs from the original")
        target.write_text(e.new_content, encoding="utf-8", newline="")
    return copy_root
