import streamlit as st

from codemind.models import WorkflowState as S
from codemind.orchestrator.orchestrator import WorkflowError
from codemind.patching.approval import ApprovalError
from ui import components as ui


def render(orch) -> None:
    ctx = orch.ctx
    st.header("Proposed Changes")
    st.markdown('<div class="cm-note">Original files are <b>never</b> modified. An approved patch is applied to a '
                'separate working copy, then validated. Nothing is committed or pushed.</div>', unsafe_allow_html=True)
    st.write("")
    p = ctx.current_proposal
    if p is None:
        st.info("No proposal yet. Pick a finding on **Findings & Explainability** and ask for a fix.")
        return
    f = ctx.finding(p.finding_id)
    awaiting = ctx.state is S.AWAITING_APPROVAL
    ui.html(ui.state_pill(ctx.state) + ui.severity_pill(f.severity))
    st.subheader(f"{p.patch_id}: {p.strategy_name}")
    st.caption(f"For {f.id} · {f.title} · attempt {p.attempt} · patch hash {p.patch_hash[:16]}…")
    st.markdown(f"**Root cause.** {p.root_cause}")
    st.markdown(f"**Intended behaviour.** {p.intended_behaviour}")
    st.code(p.unified_diff, language="diff")
    a, b, c = st.columns(3)
    a.markdown("**Affected files**  \n" + "\n".join(f"- `{x}`" for x in p.affected_files))
    b.markdown("**Possible regressions**  \n" + "\n".join(f"- {x}" for x in p.regression_risks))
    c.markdown("**Suggested tests**  \n" + "\n".join(f"- {x}" for x in p.suggested_tests))
    review = ctx.reviews.get(p.patch_id)
    if review:
        if review.ok:
            st.success("Critic review: edits stay inside the finding's file, the file compiles, and the rule no "
                       "longer matches. Ready for your decision.")
        else:
            st.error("Critic review issues: " + "; ".join(review.issues))

    note = st.text_input("Optional note for the decision log", key=f"note_{p.patch_hash[:12]}")
    col1, col2, _ = st.columns([2, 1, 3])
    approve = col1.button("Approve and validate", key=f"approve_{p.patch_hash}", type="primary", disabled=not awaiting)
    reject = col2.button("Reject", key=f"reject_{p.patch_hash}", disabled=not awaiting)
    if approve or reject:
        try:
            if approve:
                with st.spinner("Applying to a working copy and running checks…"):
                    orch.approve(p.patch_id, p.patch_hash, note)
                v = ctx.latest_validation
                if ctx.state is S.AWAITING_APPROVAL:
                    ui.flash_error(f"Validation of {p.patch_id} FAILED. The Code Improvement Agent proposed a "
                                   f"different strategy ({ctx.current_proposal.strategy_name}); it needs your approval.")
                elif ctx.state is S.BLOCKED:
                    ui.flash_error(f"Stopped: {ctx.blocked_reason}")
                else:
                    ui.flash_ok(f"Validation result: {v.status.value}. See Validation Results.")
                    st.session_state.goto = {"nav": "7. Validation Results"}
            else:
                orch.reject(p.patch_id, p.patch_hash, note)
                ui.flash_ok(f"Rejected {p.patch_id}. The original is unchanged and no working copy was made.")
        except (ApprovalError, WorkflowError) as exc:
            ui.flash_error(f"Refused: {exc}")
        st.rerun()
    if not awaiting:
        decision = next((x.decision for x in reversed(ctx.approvals) if x.patch_id == p.patch_id), None)
        st.caption(f"This proposal is no longer awaiting a decision ({decision or ui.state_label(ctx.state)}).")

    if len(ctx.proposals) > 1:
        with st.expander(f"Proposal history ({len(ctx.proposals)})"):
            for q in reversed(ctx.proposals):
                d = next((x.decision for x in reversed(ctx.approvals) if x.patch_id == q.patch_id), "no decision")
                v = next((x.status.value for x in ctx.validations if x.patch_id == q.patch_id), "not validated")
                st.write(f"- {q.patch_id} · {q.strategy_name} · {d} · {v}")
