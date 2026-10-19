import streamlit as st

from codemind.analysis.prioritizer import severity_counts
from codemind.models import Severity
from ui import components as ui


def render(orch) -> None:
    ctx = orch.ctx
    st.title("CodeMind AI")
    st.caption("An Agentic AI Code Review Assistant for Understanding, Debugging, and Improving AI-Generated Code")
    ui.html('<div class="cm-flow"><span>ANALYZE</span>→<span>EXPLAIN WITH EVIDENCE</span>→'
            '<span>COMPARE SOLUTIONS</span>→<span>HUMAN APPROVAL</span>→<span>APPLY TO COPY</span>→'
            '<span>VALIDATE</span>→<span>REPORT</span></div>')
    st.write("")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Workflow state", ctx.state.value.replace("_", " ").title())
    c2.metric("Files analysed", len(ctx.snapshot.included_files) if ctx.snapshot else 0)
    c3.metric("Findings", len(ctx.findings))
    v = ctx.latest_validation
    c4.metric("Latest validation", v.status.value if v else "None yet")

    if ctx.blocked_reason:
        st.error(f"Blocked: {ctx.blocked_reason}")
    if ctx.summary is None:
        st.markdown('<div class="cm-note">Start on <b>2. Upload &amp; Explorer</b>: load the bundled synthetic '
                    'sample or upload a ZIP of a Python project.</div>', unsafe_allow_html=True)
        return

    s = ctx.summary
    left, right = st.columns([3, 2])
    with left:
        st.subheader(s.title)
        st.write(s.purpose)
        st.markdown(f"**Technologies:** {', '.join(s.technologies) or 'none detected'}  \n"
                    f"**Entry points:** {', '.join(s.entry_points) or 'none'}  \n"
                    f"**Dependencies:** {', '.join(s.dependencies) or 'none declared'}")
    with right:
        st.subheader("Findings by severity")
        counts = severity_counts(ctx.findings)
        if counts:
            order = [sev.value for sev in Severity if sev.value in counts]
            st.bar_chart({"severity": order, "findings": [counts[o] for o in order]}, x="severity", y="findings",
                         horizontal=True, height=180, sort=False)
        else:
            st.write("No rule matched. That is not proof the code is correct.")
        if ctx.baseline:
            b = ctx.baseline
            st.caption(f"Baseline tests on the original: {b.tests_passed} passed, {b.tests_failed} failed, "
                       f"{b.tests_errors} errors.")
    if ctx.findings:
        top = ctx.findings[0]
        st.info(f"Suggested next action: review **{top.id}** ({top.severity.value}, {top.confidence.value}) "
                f"{top.title} at `{top.file}:{top.line}`.")
