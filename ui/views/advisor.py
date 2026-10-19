import streamlit as st

from ui import components as ui


def render(orch) -> None:
    ctx = orch.ctx
    st.header("Architecture Advisor")
    if ui.need_analysis(orch):
        return
    if not ctx.recommendations:
        st.info("No findings, so there is nothing to compare.")
        return
    st.caption(f"Comparisons come from a curated knowledge base filled with project facts. Text source: {ctx.llm_label}.")
    ids = list(ctx.recommendations)
    fid = st.selectbox("Finding", ids, key="advisor_pick", format_func=lambda i: f"{i} · {ctx.finding(i).title.replace(chr(96), '')}")
    r = ctx.recommendations[fid]
    st.markdown(f"**Current approach:** {r.current_approach}")
    st.dataframe([{"alternative": a.name, "advantages": "; ".join(a.pros), "disadvantages": "; ".join(a.cons),
                   "cost": a.cost, "complexity": a.complexity, "maintainability": a.maintainability,
                   "performance": a.performance} for a in r.alternatives],
                 hide_index=True, width="stretch")
    if r.keep_current:
        st.success("Keeping the current approach is acceptable here. " + r.next_action)
    st.markdown(f"**Recommended:** {r.recommended}")
    st.markdown(f"**Why:** {r.rationale}")
    st.markdown("**Assumptions**")
    for a in r.assumptions:
        st.write("- " + a)
    st.markdown(f"**Next action:** {r.next_action}")
    st.caption(f"Text origin: {r.text_origin}")
