import streamlit as st

from codemind import config
from ui import components as ui

ICON = {"done": "✅", "pending": "⏳", "skipped": "⏭️", "failed": "❌"}


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
    c1.metric("State", ctx.state.value)
    c2.metric("Retries for current finding", f"{ctx.retries} / {config.MAX_RETRIES}")
    c3.metric("Agent runs logged", len(ctx.log))
    if ctx.blocked_reason:
        st.error(f"Blocked: {ctx.blocked_reason}")

    st.subheader("Task plan")
    st.dataframe([{"": ICON.get(ctx.plan.step_status.get(s.key, ""), ""), "step": s.key, "agent": s.agent,
                   "what it does": s.description, "status": ctx.plan.step_status.get(s.key, ""),
                   "why skipped": s.reason} for s in ctx.plan.steps],
                 hide_index=True, width="stretch")

    st.subheader("State transitions (decision log)")
    st.dataframe([{"time (UTC)": d.at[11:19], "from": d.from_state, "to": d.to_state, "event": d.event,
                   "reason": d.reason} for d in ctx.decisions], hide_index=True, width="stretch")

    st.subheader("Agent execution log")
    for i, e in enumerate(ctx.log):
        label = f"{'❌' if e.error else '•'} {e.agent}: {e.summary}"
        with st.expander(label, expanded=bool(e.error)):
            st.caption(f"{e.started_at} → {e.finished_at} · state {e.state_before} → {e.state_after}")
            for o in e.outputs:
                st.write("- " + o)
            if e.error:
                st.error(e.error)
