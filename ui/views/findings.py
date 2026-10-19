import streamlit as st

from codemind.orchestrator.orchestrator import WorkflowError
from codemind.orchestrator.states import can_transition
from ui import components as ui


def render(orch) -> None:
    ctx = orch.ctx
    st.header("Findings & Explainability")
    if ui.need_analysis(orch):
        return
    if not ctx.findings:
        st.success("No rule matched. This only means none of the 9 rules fired; it does not prove the code is correct.")
        return
    st.caption("Confidence: **Confirmed** = reproduced by a real test run · **Likely** = strong pattern · "
               "**Potential** = needs human review. Findings are signals, not proof.")
    st.dataframe([{"ID": f.id, "severity": f.severity.value, "confidence": f.confidence.value,
                   "category": f.category, "title": f.title.replace("`", ""), "location": f"{f.file}:{f.line}",
                   "verification": f.verification.value} for f in ctx.findings],
                 hide_index=True, width="stretch")

    ids = [f.id for f in ctx.findings]
    default = ids.index(ctx.selected_finding_id) if ctx.selected_finding_id in ids else 0
    fid = st.selectbox("Finding details", ids, index=default, key="finding_pick",
                       format_func=lambda i: f"{i} · {ctx.finding(i).title.replace(chr(96), '')}")
    f = ctx.finding(fid)
    ui.html(ui.severity_pill(f.severity) + ui.pill(f.confidence.value, "#9E2A4B") + ui.pill(f.category, "#475467")
            + ui.pill(f.rule_id, "#344054"))
    st.markdown(f"#### {f.title}")
    st.caption(f"{f.file}, line {f.line} · {f.extra.get('detail', '')}")
    st.code(f.evidence.snippet, language="text")
    a, b = st.columns(2)
    a.markdown(f"**Why it is a problem**  \n{f.why_problematic}")
    a.markdown(f"**Potential impact**  \n{f.impact}")
    b.markdown(f"**Suggested remediation**  \n{f.remediation}")
    b.markdown(f"**How a fix will be validated**  \n{f.validation_method}")
    if f.extra.get("confirmed_by"):
        st.warning("Confirmed by the baseline test run on the original code: " + ", ".join(f.extra["confirmed_by"]))

    allowed = can_transition(ctx.state, "finding_selected")
    if st.button("Ask the Code Improvement Agent for a fix", key=f"propose_{fid}", type="primary", disabled=not allowed):
        try:
            orch.select_finding(fid)
            if ctx.state.value == "AWAITING_APPROVAL":
                ui.flash_ok(f"Proposal ready for {fid}. Review it below and approve or reject.")
                st.session_state.goto = {"nav": "6. Proposed Changes"}
            elif ctx.state.value == "FINDINGS_READY":
                ui.flash_error(ctx.log[-1].summary)
            else:
                ui.flash_error(ctx.blocked_reason or "No proposal could be produced.")
        except WorkflowError as exc:
            ui.flash_error(str(exc))
        st.rerun()
    if not allowed:
        st.caption(f"A proposal is in progress (state {ctx.state.value}). Finish it on Proposed Changes first.")
