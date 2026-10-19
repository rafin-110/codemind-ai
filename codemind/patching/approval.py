"""Human approval bound to the exact patch and the exact original source.

An approval is only valid for one proposal: same patch_id, same patch_hash, same base
snapshot hash, and the original file contents must still match. Anything else is stale.
"""

from __future__ import annotations

from codemind.agents.code_improvement import source_hash_matches
from codemind.workspace import safe_join
from codemind.models import ApprovalRecord, PatchProposal, WorkflowContext, WorkflowState, compute_patch_hash, utc_now


class ApprovalError(ValueError):
    """The approval or rejection does not match the current proposal."""


def check_binding(ctx: WorkflowContext, proposal: PatchProposal, presented_hash: str) -> None:
    if ctx.state is not WorkflowState.AWAITING_APPROVAL:
        raise ApprovalError(f"no proposal is awaiting approval (state is {ctx.state.value})")
    current = ctx.current_proposal
    if current is None or current.patch_id != proposal.patch_id:
        raise ApprovalError("this is not the current proposal; it has been superseded")
    if presented_hash != proposal.patch_hash:
        raise ApprovalError("approval hash does not match the proposal (stale or tampered approval)")
    if compute_patch_hash(proposal.edits, proposal.base_snapshot_hash) != proposal.patch_hash:
        raise ApprovalError("proposal content changed after it was shown")
    if proposal.base_snapshot_hash != ctx.snapshot.snapshot_hash:
        raise ApprovalError("repository changed since the proposal was created")
    for e in proposal.edits:
        try:
            safe_join(ctx.snapshot.root, e.rel_path)
        except ValueError as exc:
            raise ApprovalError(f"unsafe patch path: {exc}") from exc
    if not source_hash_matches(ctx, proposal):
        raise ApprovalError("original source file changed since the proposal was created")


def record(ctx: WorkflowContext, proposal: PatchProposal, decision: str, presented_hash: str,
           note: str = "") -> ApprovalRecord:
    if decision not in ("approved", "rejected"):
        raise ApprovalError(f"unknown decision {decision!r}")
    check_binding(ctx, proposal, presented_hash)
    rec = ApprovalRecord(proposal.patch_id, proposal.patch_hash, proposal.base_snapshot_hash,
                         decision, utc_now(), note)
    ctx.approvals.append(rec)
    return rec


def valid_approval(ctx: WorkflowContext, proposal: PatchProposal) -> ApprovalRecord | None:
    for rec in reversed(ctx.approvals):
        if rec.patch_id == proposal.patch_id:
            ok = (rec.decision == "approved" and rec.patch_hash == proposal.patch_hash
                  and rec.base_snapshot_hash == ctx.snapshot.snapshot_hash
                  and compute_patch_hash(proposal.edits, proposal.base_snapshot_hash) == proposal.patch_hash)
            return rec if ok else None
    return None
