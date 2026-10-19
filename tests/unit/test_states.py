"""T-STM-01: the transition table is enforced."""

import pytest

from codemind.models import WorkflowContext, WorkflowState as S
from codemind.orchestrator.states import (
    TRANSITIONS, IllegalTransition, can_transition, force_blocked, transition,
)


def test_happy_path_sequence_records_decisions():
    ctx = WorkflowContext(run_id="r1")
    for event in ["plan_created", "analysis_started", "analysis_complete", "finding_selected",
                  "critic_approved", "human_approved", "validation_started", "validation_passed"]:
        transition(ctx, event, reason="test")
    assert ctx.state is S.VALIDATED
    assert [d.event for d in ctx.decisions][-1] == "validation_passed"
    assert len(ctx.decisions) == 8


def test_rejection_returns_to_findings():
    ctx = WorkflowContext(run_id="r2", state=S.AWAITING_APPROVAL)
    transition(ctx, "human_rejected")
    assert ctx.state is S.FINDINGS_READY


def test_failed_validation_can_retry_or_block():
    ctx = WorkflowContext(run_id="r3", state=S.VALIDATION_FAILED)
    assert can_transition(ctx.state, "retry_proposed")
    transition(ctx, "retries_exhausted")
    assert ctx.state is S.BLOCKED


@pytest.mark.parametrize("state,event", [
    (S.RECEIVED, "human_approved"),          # cannot approve before analysis
    (S.FINDINGS_READY, "human_approved"),    # cannot approve without a proposal
    (S.PATCH_PROPOSED, "human_approved"),    # critic must review first
    (S.AWAITING_APPROVAL, "validation_started"),  # cannot validate unapplied patch
    (S.VALIDATED, "human_approved"),
])
def test_illegal_transitions_raise(state, event):
    ctx = WorkflowContext(run_id="r4", state=state)
    with pytest.raises(IllegalTransition):
        transition(ctx, event)
    assert ctx.state is state
    assert ctx.decisions == []


def test_only_path_to_patch_application_is_human_approval():
    sources = [k for k, v in TRANSITIONS.items() if v is S.PATCH_APPLIED_TO_COPY]
    assert sources == [(S.AWAITING_APPROVAL, "human_approved")]


def test_force_blocked_from_any_state():
    ctx = WorkflowContext(run_id="r5", state=S.ANALYZING)
    force_blocked(ctx, "boom")
    assert ctx.state is S.BLOCKED and ctx.blocked_reason == "boom"
