"""Small presentation helpers shared by the views. No analysis logic lives here."""

from __future__ import annotations

import streamlit as st

from codemind.models import Severity, ValidationStatus, WorkflowState

SEVERITY_COLOR = {
    Severity.CRITICAL: "#b42318", Severity.HIGH: "#c4320a", Severity.MEDIUM: "#b54708",
    Severity.LOW: "#475467", Severity.INFO: "#475467",
}
STATUS_COLOR = {
    ValidationStatus.PASSED: "#067647", ValidationStatus.FAILED: "#b42318",
    ValidationStatus.NOT_RUN: "#475467", ValidationStatus.BLOCKED: "#b42318",
    ValidationStatus.PARTIALLY_VERIFIED: "#b54708",
}
STATE_COLOR = {
    WorkflowState.VALIDATED: "#067647", WorkflowState.BLOCKED: "#b42318",
    WorkflowState.VALIDATION_FAILED: "#b42318", WorkflowState.AWAITING_APPROVAL: "#7B1E3A",
    WorkflowState.PARTIALLY_VERIFIED: "#b54708",
}

CSS = """
<style>
:root {--wine:#7B1E3A;--wine-deep:#4F0F23;--rose:#9E2A4B;--cream:#FBF5EA;--parch:#F1E4CF;
       --line:#E3D2B8;--ink:#3B1420;--muted:#7A5C61;--card:#FFFDF8}
.stApp {background:var(--cream)}
.block-container {padding-top:2.4rem;padding-bottom:2rem;max-width:1240px}
[data-testid="stVerticalBlock"] {gap:.65rem}
h1 {font-size:1.7rem !important;font-weight:700 !important;color:var(--wine) !important;
    letter-spacing:-.01em;padding:0 0 .1rem 0 !important}
h2 {font-size:1.3rem !important;font-weight:650 !important;color:var(--wine) !important;padding:.2rem 0 !important}
h3 {font-size:1.02rem !important;font-weight:650 !important;color:var(--ink) !important;padding:.2rem 0 !important}
hr {margin:.8rem 0 !important;border-color:var(--line) !important}
[data-testid="stCaptionContainer"] {color:var(--muted)}

/* sidebar */
section[data-testid="stSidebar"] {background:linear-gradient(180deg,var(--wine-deep),var(--wine));border-right:0}
section[data-testid="stSidebar"] * {color:var(--cream)}
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {color:#E9D6BC;opacity:.92}
section[data-testid="stSidebar"] hr {border-color:rgba(251,245,234,.25) !important}
section[data-testid="stSidebar"] div[role="radiogroup"] {gap:2px}
section[data-testid="stSidebar"] div[role="radiogroup"] label {padding:5px 10px;border-radius:8px;width:100%}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {background:rgba(251,245,234,.14)}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {background:var(--cream)}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) * {
    color:var(--wine) !important;font-weight:650}

/* metrics as compact cards */
[data-testid="stMetric"] {background:var(--card);border:1px solid var(--line);border-left:4px solid var(--wine);
                          border-radius:8px;padding:.45rem .8rem}
[data-testid="stMetricLabel"] p {font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
[data-testid="stMetricValue"] {color:var(--wine)}
[data-testid="stMetricValue"] > div {font-size:1.25rem;white-space:normal;line-height:1.25}

/* buttons */
.stButton > button, .stDownloadButton > button {
    border-radius:8px;padding:.28rem .9rem;font-weight:600;border:1px solid var(--wine);
    color:var(--wine);background:var(--card)}
.stButton > button:hover, .stDownloadButton > button:hover {
    background:var(--parch);border-color:var(--wine-deep);color:var(--wine-deep)}
.stButton > button[kind="primary"], button[data-testid="stBaseButton-primary"] {
    background:var(--wine);color:var(--cream);border-color:var(--wine)}
.stButton > button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover {
    background:var(--wine-deep);color:#fff}
.stButton > button:disabled, .stDownloadButton > button:disabled {opacity:.45}

/* containers */
[data-testid="stExpander"] {border:1px solid var(--line);border-radius:8px;background:var(--card)}
[data-testid="stAlert"] {border-radius:8px;padding:.45rem .8rem}
[data-testid="stDataFrame"] {border:1px solid var(--line);border-radius:8px;overflow:hidden}
[data-testid="stCode"] pre, pre {background:#F6ECDD !important;border:1px solid var(--line);
                                  border-radius:8px;font-size:.8rem}
[data-testid="stFileUploader"] section {background:var(--card);border:1px dashed var(--rose);border-radius:8px}

/* custom pieces */
.cm-pill {display:inline-block;padding:2px 10px;border-radius:999px;font-size:0.76rem;font-weight:600;
          color:#fff !important;margin-right:6px;white-space:nowrap}
.cm-flow {font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:0.78rem;line-height:2}
.cm-flow span {background:var(--parch);border:1px solid var(--line);color:var(--wine);border-radius:6px;
               padding:2px 7px;margin:0 2px;white-space:nowrap;font-weight:600}
.cm-note {border-left:4px solid var(--wine);padding:6px 12px;background:var(--parch);border-radius:4px;
          font-size:.9rem}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def pill(text: str, color: str = "#475467") -> str:
    return f'<span class="cm-pill" style="background:{color}">{text}</span>'


def severity_pill(sev: Severity) -> str:
    return pill(sev.value, SEVERITY_COLOR.get(sev, "#475467"))


def status_pill(status: ValidationStatus) -> str:
    return pill(status.value, STATUS_COLOR.get(status, "#475467"))


def state_pill(state: WorkflowState) -> str:
    return pill(state.value, STATE_COLOR.get(state, "#9E2A4B"))


def html(text: str) -> None:
    st.markdown(text, unsafe_allow_html=True)


def flash_error(message: str) -> None:
    st.session_state["flash"] = ("error", message)


def flash_ok(message: str) -> None:
    st.session_state["flash"] = ("success", message)


def show_flash() -> None:
    kind, msg = st.session_state.pop("flash", (None, None))
    if kind == "error":
        st.error(msg)
    elif kind == "success":
        st.success(msg)


def baseline_panel(ctx) -> None:
    """Show the baseline test run honestly: counts when tests ran, the reason when they did not."""
    b = ctx.baseline
    if b is None:
        from codemind.agents.critic_validator import tests_allowed   # lazy: keeps this module light
        if ctx.summary is None:
            return
        allowed, why = tests_allowed(ctx)
        st.caption("Baseline tests were not run. "
                   + (why or "They run as part of the analysis once you start it."))
        return
    reason = b.checks[0].detail if b.checks else ""
    ui_status = status_pill(b.status)
    if b.status in (ValidationStatus.NOT_RUN, ValidationStatus.BLOCKED):
        html("Baseline tests " + ui_status)
        st.warning(f"The baseline tests produced no results, so nothing was confirmed by execution. {reason}")
    else:
        html("Baseline tests " + ui_status)
        st.write(f"{b.tests_passed} passed, {b.tests_failed} failed, {b.tests_errors} errors, "
                 f"{b.tests_skipped} skipped on the untouched original. Findings whose line appears in a "
                 "failing test's traceback are marked Confirmed.")
    if b.raw_output_tail:
        with st.expander("Baseline test output (last lines)"):
            st.code(b.raw_output_tail, language="text")


def need_analysis(orch) -> bool:
    """Show a hint and return True when there is nothing to display yet."""
    if orch.ctx.summary is None:
        st.info("Load a repository and run the analysis on **Upload & Explorer** first.")
        return True
    return False
