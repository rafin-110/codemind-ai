"""Explicit workflow state machine (ARCHITECTURE.md section 4).

The transition table is the single source of truth for what may happen next.
Anything not in the table raises `IllegalTransition`.
"""

from __future__ import annotations

from codemind.models import DecisionRecord, WorkflowContext, WorkflowState as S


class IllegalTransition(RuntimeError):
    pass


# (from_state, event) -> to_state
TRANSITIONS: dict[tuple[S, str], S] = {
    (S.RECEIVED, "plan_created"): S.PLANNED,
    (S.RECEIVED, "ingest_failed"): S.BLOCKED,
    (S.PLANNED, "analysis_started"): S.ANALYZING,
    (S.ANALYZING, "analysis_complete"): S.FINDINGS_READY,
    (S.FINDINGS_READY, "finding_selected"): S.PATCH_PROPOSED,
    (S.PATCH_PROPOSED, "critic_rejected"): S.PATCH_PROPOSED,
    (S.PATCH_PROPOSED, "critic_approved"): S.AWAITING_APPROVAL,
    (S.PATCH_PROPOSED, "no_fix_available"): S.FINDINGS_READY,
    (S.PATCH_PROPOSED, "no_strategy_left"): S.BLOCKED,
    (S.PATCH_PROPOSED, "critic_retries_exhausted"): S.BLOCKED,
    (S.AWAITING_APPROVAL, "human_rejected"): S.FINDINGS_READY,
    (S.AWAITING_APPROVAL, "human_approved"): S.PATCH_APPLIED_TO_COPY,
    (S.PATCH_APPLIED_TO_COPY, "validation_started"): S.VALIDATING,
    (S.VALIDATING, "validation_passed"): S.VALIDATED,
    (S.VALIDATING, "validation_partial"): S.PARTIALLY_VERIFIED,
    (S.VALIDATING, "validation_failed"): S.VALIDATION_FAILED,
    (S.VALIDATING, "validation_blocked"): S.BLOCKED,
    (S.VALIDATION_FAILED, "retry_proposed"): S.PATCH_PROPOSED,
    (S.VALIDATION_FAILED, "retries_exhausted"): S.BLOCKED,
    # after a finished patch cycle the developer may pick another finding
    (S.VALIDATED, "finding_selected"): S.PATCH_PROPOSED,
    (S.PARTIALLY_VERIFIED, "finding_selected"): S.PATCH_PROPOSED,
    (S.BLOCKED, "finding_selected"): S.PATCH_PROPOSED,
    (S.FINDINGS_READY, "back_to_findings"): S.FINDINGS_READY,
    (S.VALIDATED, "back_to_findings"): S.FINDINGS_READY,
    (S.PARTIALLY_VERIFIED, "back_to_findings"): S.FINDINGS_READY,
    (S.BLOCKED, "back_to_findings"): S.FINDINGS_READY,
}

# A BLOCKED caused by ingestion has no snapshot, so finding_selected from there is
# rejected by the orchestrator's guard rather than the table.

TERMINAL_FOR_CYCLE = {S.VALIDATED, S.PARTIALLY_VERIFIED, S.BLOCKED}


def can_transition(state: S, event: str) -> bool:
    return (state, event) in TRANSITIONS


def transition(ctx: WorkflowContext, event: str, reason: str = "") -> S:
    """Move `ctx` to the next state, recording the decision. Raises on illegal moves."""
    key = (ctx.state, event)
    if key not in TRANSITIONS:
        raise IllegalTransition(f"Event '{event}' is not allowed in state {ctx.state.value}")
    new_state = TRANSITIONS[key]
    ctx.decisions.append(DecisionRecord(ctx.state.value, new_state.value, event, reason))
    ctx.state = new_state
    return new_state


def force_blocked(ctx: WorkflowContext, reason: str) -> None:
    """Used only for unexpected exceptions: any state may fail safe into BLOCKED."""
    ctx.decisions.append(DecisionRecord(ctx.state.value, S.BLOCKED.value, "unexpected_error", reason))
    ctx.state = S.BLOCKED
    ctx.blocked_reason = reason
