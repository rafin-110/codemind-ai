"""T-STM-01: the transition table is enforced, and states that claim a result need evidence."""

import pytest

from codemind.models import (
    AnalysisStatus as A, ApprovalRecord, CriticReview, PatchProposal, ValidationResult,
    ValidationStatus as V, WorkflowContext, WorkflowState as S,
)
from codemind.orchestrator.states import (
    TRANSITIONS, IllegalTransition, can_transition, force_blocked, transition,
)


def _proposal(ctx, patch_id="P-1"):
    p = PatchProposal(patch_id, "F-001", 0, "s", "rc", "ib", [], "", [], [], [], "base", "hash-" + patch_id)
    ctx.proposals.append(p)
    return p


def _validation(ctx, status, patch_id="P-1", unchanged=True):
    ctx.validations.append(ValidationResult(patch_id, status, [], original_unchanged=unchanged))


def test_happy_path_sequence_records_decisions():
    ctx = WorkflowContext(run_id="r1")
    transition(ctx, "plan_created")
    transition(ctx, "analysis_started")
    ctx.analysis_status = A.COMPLETED
    transition(ctx, "analysis_complete")
    transition(ctx, "finding_selected")
    p = _proposal(ctx)
    ctx.reviews[p.patch_id] = CriticReview(p.patch_id, True, True, [])
    transition(ctx, "critic_approved")
    ctx.approvals.append(ApprovalRecord(p.patch_id, p.patch_hash, "base", "approved", "now"))
    transition(ctx, "human_approved")
    transition(ctx, "validation_started")
    _validation(ctx, V.PASSED)
    transition(ctx, "validation_passed", reason="test")
    assert ctx.state is S.VALIDATED
    assert [d.event for d in ctx.decisions][-1] == "validation_passed"
    assert len(ctx.decisions) == 8


def test_rejection_returns_to_findings():
    ctx = WorkflowContext(run_id="r2", state=S.AWAITING_APPROVAL, analysis_status=A.COMPLETED)
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


# ------------------------------------------------------------ evidence guards

def _refused(ctx, event, match):
    before = ctx.state
    with pytest.raises(IllegalTransition, match=match):
        transition(ctx, event)
    assert ctx.state is before and ctx.decisions == []      # nothing recorded on refusal


def test_findings_ready_needs_completed_analysis():
    for status in (A.NOT_STARTED, A.FAILED):
        _refused(WorkflowContext(run_id="e1", state=S.ANALYZING, analysis_status=status),
                 "analysis_complete", "analysis is not complete")


def test_awaiting_approval_needs_passed_critic_review():
    ctx = WorkflowContext(run_id="e2", state=S.PATCH_PROPOSED)
    _refused(ctx, "critic_approved", "critic review")              # no proposal at all
    p = _proposal(ctx)
    ctx.reviews[p.patch_id] = CriticReview(p.patch_id, True, False, ["rule still matches"])
    _refused(ctx, "critic_approved", "critic review")              # review exists but rejected


def test_patch_application_needs_approval_of_current_patch():
    ctx = WorkflowContext(run_id="e3", state=S.AWAITING_APPROVAL)
    old = _proposal(ctx, "P-old")
    ctx.approvals.append(ApprovalRecord(old.patch_id, old.patch_hash, "base", "approved", "now"))
    _proposal(ctx, "P-new")                                         # approval was for a superseded patch
    _refused(ctx, "human_approved", "no human approval")


@pytest.mark.parametrize("event,status", [
    ("validation_passed", V.FAILED),
    ("validation_passed", V.PARTIALLY_VERIFIED),       # static checks only is not "Passed"
    ("validation_partial", V.PASSED),
    ("validation_failed", V.PASSED),
])
def test_validation_result_states_must_match_the_result(event, status):
    ctx = WorkflowContext(run_id="e4", state=S.VALIDATING)
    _proposal(ctx)
    _validation(ctx, status)
    _refused(ctx, event, "latest validation is")


def test_validated_needs_a_result_for_the_current_patch_and_untouched_original():
    ctx = WorkflowContext(run_id="e5", state=S.VALIDATING)
    _proposal(ctx)
    _refused(ctx, "validation_passed", "no validation result")
    _validation(ctx, V.PASSED, patch_id="P-other")
    _refused(ctx, "validation_passed", "no validation result")
    _validation(ctx, V.PASSED, unchanged=None)
    _refused(ctx, "validation_passed", "not confirmed unchanged")
