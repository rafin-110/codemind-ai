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
.cm-pill {display:inline-block;padding:2px 10px;border-radius:999px;font-size:0.78rem;font-weight:600;
          color:#fff;margin-right:6px;white-space:nowrap}
.cm-flow {font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:0.82rem;line-height:1.9}
.cm-flow span {background:rgba(123,30,58,0.08);border:1px solid rgba(123,30,58,0.35);border-radius:6px;
               padding:2px 7px;margin:0 2px;white-space:nowrap}
.cm-note {border-left:4px solid #7B1E3A;padding:6px 12px;background:rgba(123,30,58,0.06);border-radius:4px}
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


def need_analysis(orch) -> bool:
    """Show a hint and return True when there is nothing to display yet."""
    if orch.ctx.summary is None:
        st.info("Load a repository and run the analysis on **Upload & Explorer** first.")
        return True
    return False
