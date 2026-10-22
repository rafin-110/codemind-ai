import pandas as pd
import streamlit as st

from codemind import config
from codemind.models import WorkflowState
from ui import components as ui

STEP_TEXT = {"success": "#17603F", "danger": "#A02F3D", "neutral": "#4E5F5B"}


def _label(state_value: str) -> str:
    try:
        return ui.state_label(WorkflowState(state_value))
    except ValueError:
        return state_value


def render(orch) -> None:
    ctx = orch.ctx
    st.header("Agent Workflow")
    st.caption("The Planner builds a plan from what the repository contains; each agent writes structured "
               "results to one shared context, and every state change is logged with its reason.")
    if ctx.plan is None:
        st.info("No plan yet. Load a repository first.")
        if ctx.blocked_reason:
            st.error(ctx.blocked_reason)
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        ui.status_card("Workflow state", ui.state_pill(ctx.state))
    c2.metric("Retries for current finding", f"{ctx.retries} / {config.MAX_RETRIES}")
    c3.metric("Agent runs logged", len(ctx.log))
    if ctx.blocked_reason:
        st.error(f"Blocked: {ctx.blocked_reason}")

    st.subheader("Task plan")
    rows = [{"step": s.key, "status": ui.step_label(ctx.plan.step_status.get(s.key, "")), "agent": s.agent,
             "what it does": s.description, "why skipped": s.reason} for s in ctx.plan.steps]
    tone = {ui.step_label(k): STEP_TEXT[v] for k, v in ui.STEP_TONE.items()}
    st.dataframe(pd.DataFrame(rows).style.map(lambda x: f"color:{tone.get(x, '')};font-weight:600",
                                              subset=["status"]),
                 hide_index=True, width="stretch")

    st.subheader("State transitions (decision log)")
    st.dataframe([{"time (UTC)": d.at[11:19], "from": _label(d.from_state), "to": _label(d.to_state),
                   "event": d.event, "reason": d.reason} for d in ctx.decisions], hide_index=True, width="stretch")

    st.subheader("Agent execution log")
    for i, e in enumerate(ctx.log):
        label = f"{'Failed: ' if e.error else ''}{e.agent}: {e.summary}"
        with st.expander(label, expanded=bool(e.error)):
            st.caption(f"{e.started_at} → {e.finished_at} · state {_label(e.state_before)} → {_label(e.state_after)}")
            for o in e.outputs:
                st.write("- " + o)
            if e.error:
                st.error(e.error)
