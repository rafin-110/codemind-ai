"""Small presentation helpers shared by the views. No analysis logic lives here."""

from __future__ import annotations

import streamlit as st

from codemind.models import Severity, ValidationStatus, WorkflowState

# --- palette (Deep Forest + Teal); .streamlit/config.toml uses the same values ---------------
FOREST, TEAL = "#123B35", "#0D9488"
BG, CARD, INK, MUTED, LINE = "#F5F9F7", "#FFFFFF", "#172B28", "#667874", "#DCE7E3"

# Status tones: (accent, text, tint). The accent is the palette colour; the text is a darker shade
# of it so small labels keep at least 4.5:1 contrast on the tint.
TONES = {
    "success": ("#21845A", "#17603F", "#E7F3ED"),
    "progress": ("#2878C8", "#1D5C9B", "#E8F1FA"),
    "attention": ("#B7791F", "#7F5313", "#FAF1E3"),
    "danger": ("#C43D4D", "#A02F3D", "#FAEAEC"),
    "neutral": ("#8A9A96", "#4E5F5B", "#EEF3F1"),
}

STATE_LABEL = {
    WorkflowState.RECEIVED: "Not Started", WorkflowState.PLANNED: "Planned",
    WorkflowState.ANALYZING: "Analyzing", WorkflowState.FINDINGS_READY: "Findings Ready",
    WorkflowState.PATCH_PROPOSED: "Patch Proposed", WorkflowState.AWAITING_APPROVAL: "Awaiting Approval",
    WorkflowState.PATCH_APPLIED_TO_COPY: "Applied to Copy", WorkflowState.VALIDATING: "Validating",
    WorkflowState.VALIDATED: "Validated", WorkflowState.VALIDATION_FAILED: "Validation Failed",
    WorkflowState.PARTIALLY_VERIFIED: "Partially Verified", WorkflowState.BLOCKED: "Blocked",
}
# Only VALIDATED is green: findings or a proposal are work in progress, not a verified result.
STATE_TONE = {
    WorkflowState.RECEIVED: "neutral", WorkflowState.PLANNED: "neutral",
    WorkflowState.ANALYZING: "progress", WorkflowState.FINDINGS_READY: "progress",
    WorkflowState.PATCH_PROPOSED: "progress", WorkflowState.PATCH_APPLIED_TO_COPY: "progress",
    WorkflowState.VALIDATING: "progress", WorkflowState.AWAITING_APPROVAL: "attention",
    WorkflowState.PARTIALLY_VERIFIED: "attention", WorkflowState.VALIDATED: "success",
    WorkflowState.VALIDATION_FAILED: "danger", WorkflowState.BLOCKED: "danger",
}
STATUS_TONE = {
    ValidationStatus.PASSED: "success", ValidationStatus.FAILED: "danger",
    ValidationStatus.BLOCKED: "danger", ValidationStatus.PARTIALLY_VERIFIED: "attention",
    ValidationStatus.NOT_RUN: "neutral",
}
SEVERITY_TONE = {
    Severity.CRITICAL: "danger", Severity.HIGH: "danger", Severity.MEDIUM: "attention",
    Severity.LOW: "neutral", Severity.INFO: "neutral",
}
STEP_LABEL = {"done": "Done", "pending": "Pending", "skipped": "Skipped", "failed": "Failed"}
STEP_TONE = {"done": "success", "pending": "neutral", "skipped": "neutral", "failed": "danger"}

CSS = """
<style>
:root {--forest:#123B35;--teal:#0D9488;--teal-dark:#0B7A70;--bg:#F5F9F7;--card:#FFFFFF;
       --ink:#172B28;--muted:#667874;--line:#DCE7E3;--radius:10px}
.stApp {background:var(--bg);color:var(--ink)}

/* Layout. Streamlit's header is fixed, opaque and 3.75rem tall: the top padding must clear it,
   otherwise every page heading starts underneath it and its top is cut off. */
.block-container, [data-testid="stMainBlockContainer"] {
    padding:4.75rem 2.5rem 3rem !important;max-width:1280px;min-width:0}
@media (max-width:1200px) {
    .block-container, [data-testid="stMainBlockContainer"] {padding-left:1.5rem !important;padding-right:1.5rem !important}}
header[data-testid="stHeader"] {background:var(--bg)}
[data-testid="stVerticalBlock"] {gap:.75rem}
[data-testid="stColumn"] {min-width:0}

/* Typography: headings wrap instead of being cut, sizes stay readable */
h1, h2, h3, h4 {color:var(--ink) !important;white-space:normal !important;overflow:visible !important;
                overflow-wrap:break-word;letter-spacing:-.01em}
h1 {font-size:1.85rem !important;font-weight:700 !important;padding:0 0 .15rem !important;line-height:1.25 !important}
h2 {font-size:1.5rem !important;font-weight:700 !important;padding:0 0 .1rem !important;line-height:1.3 !important}
h3 {font-size:1.1rem !important;font-weight:650 !important;padding:.35rem 0 .1rem !important;line-height:1.35 !important}
h4 {font-size:1rem !important;font-weight:650 !important}
[data-testid="stHeaderActionElements"] {display:none}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {color:var(--muted)}
hr {margin:1rem 0 !important;border-color:var(--line) !important}

/* Streamlit puts widget labels and metric text in .stMarkdownEllipsis (nowrap + overflow hidden +
   ellipsis), which cut long labels at the right edge. Let them wrap instead. */
.stMarkdownEllipsis, .stMarkdownEllipsis p {white-space:normal !important;overflow:visible !important;
                                            text-overflow:clip !important}

/* sidebar */
section[data-testid="stSidebar"] {background:var(--forest);border-right:1px solid #0C2A26}
section[data-testid="stSidebar"] * {color:#E6F0ED}
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {color:#A9C2BC}
section[data-testid="stSidebar"] hr {border-color:rgba(230,240,237,.14) !important;margin:.9rem 0 !important}
section[data-testid="stSidebar"] div[role="radiogroup"] {gap:2px}
section[data-testid="stSidebar"] div[role="radiogroup"] label {padding:7px 12px;border-radius:8px;width:100%;
    margin:0;border-left:3px solid transparent}
/* nav: hide the radio circle, show the active page as a teal-edged row */
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div > div:not([data-testid="stMarkdownContainer"]) {
    display:none}
section[data-testid="stSidebar"] div[role="radiogroup"] label p {font-size:.92rem;color:#C9DBD6}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {background:rgba(255,255,255,.06)}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] {
    background:rgba(13,148,136,.22);border-left-color:var(--teal)}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] p {
    color:#FFFFFF;font-weight:600}
section[data-testid="stSidebar"] p.cm-brand {font-size:1.3rem;font-weight:700;color:#FFFFFF;letter-spacing:-.01em;
                                             margin:0;line-height:1.3}
section[data-testid="stSidebar"] p.cm-brand-sub {font-size:.8rem;line-height:1.45;color:#A9C2BC;margin:.3rem 0 0}
section[data-testid="stSidebar"] p.cm-side-label {font-size:.7rem;font-weight:600;text-transform:uppercase;
    letter-spacing:.08em;color:#8FB0A9;margin:0 0 .4rem}
.cm-side-card {background:rgba(255,255,255,.05);border:1px solid rgba(230,240,237,.12);border-radius:8px;
               padding:.6rem .75rem;margin-bottom:.6rem;overflow-wrap:anywhere}
section[data-testid="stSidebar"] .cm-side-value {font-size:.88rem;color:#FFFFFF;font-weight:500}
section[data-testid="stSidebar"] p.cm-side-note {font-size:.78rem;line-height:1.45;color:#A9C2BC;margin-top:.2rem}
section[data-testid="stSidebar"] .cm-pill {margin:0}

/* metric cards */
[data-testid="stMetric"] {background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
                          padding:.7rem .9rem}
[data-testid="stMetricLabel"] p {font-size:.8rem;color:var(--muted);font-weight:500}
[data-testid="stMetricValue"] {color:var(--ink);font-size:1.45rem;line-height:1.25}

/* buttons */
.stButton > button, .stDownloadButton > button {
    border-radius:8px;padding:.4rem 1rem;font-weight:600;border:1px solid var(--line);color:var(--ink);
    background:var(--card);height:auto;min-height:2.4rem}
.stButton > button p, .stDownloadButton > button p {white-space:normal}
.stButton > button:hover, .stDownloadButton > button:hover {border-color:var(--teal);color:var(--teal-dark);
    background:#F0F8F6}
.stButton > button[kind="primary"], button[data-testid="stBaseButton-primary"] {
    background:var(--teal);color:#FFFFFF;border-color:var(--teal)}
.stButton > button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover {
    background:var(--teal-dark);border-color:var(--teal-dark);color:#FFFFFF}
.stButton > button:disabled, .stDownloadButton > button:disabled {opacity:.5}

/* panels, tables, code. Wide content scrolls inside its own box, never the page. */
[data-testid="stExpander"] details {border:1px solid var(--line);border-radius:var(--radius);background:var(--card)}
[data-testid="stExpander"] summary p {white-space:normal;overflow-wrap:anywhere}
[data-testid="stAlert"] {border-radius:var(--radius)}
[data-testid="stDataFrame"] {border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;max-width:100%}
[data-testid="stCode"] {max-width:100%}
[data-testid="stCode"] pre {background:#FBFDFC !important;border:1px solid var(--line);border-radius:var(--radius);
                            font-size:.8rem;overflow-x:auto;max-width:100%}
[data-testid="stFileUploader"] section {background:var(--card);border:1px dashed #A7C4BD;border-radius:var(--radius)}
[data-testid="stMarkdownContainer"] code {background:#EAF3F0;color:#0F5F57;border-radius:4px;padding:.05rem .3rem;
                                          overflow-wrap:anywhere}

/* custom pieces */
.cm-pill {display:inline-flex;align-items:center;gap:6px;padding:2px 10px 2px 8px;border-radius:999px;
          font-size:.78rem;font-weight:600;line-height:1.5;margin:0 6px 4px 0;border:1px solid}
.cm-pill::before {content:"";width:7px;height:7px;border-radius:50%;background:var(--dot);flex:none}
.cm-status-card {background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
                 padding:.7rem .9rem;min-height:5.4rem}
.cm-status-card .cm-label {font-size:.8rem;color:var(--muted);font-weight:500;margin-bottom:.45rem}
.cm-status-card .cm-pill {font-size:.9rem;padding:3px 12px 3px 10px}
.cm-steps {display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:.25rem 0 .5rem}
.cm-steps span {background:var(--card);border:1px solid var(--line);color:var(--ink);border-radius:6px;
                padding:3px 9px;font-size:.8rem;font-weight:500}
.cm-steps i {color:var(--muted);font-style:normal;font-size:.8rem}
.cm-note {border:1px solid var(--line);border-left:3px solid var(--teal);padding:.6rem .9rem;background:var(--card);
          border-radius:8px;font-size:.92rem;color:var(--ink)}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def pill(text: str, tone: str = "neutral") -> str:
    accent, fg, tint = TONES.get(tone, TONES["neutral"])
    return (f'<span class="cm-pill" style="--dot:{accent};color:{fg};background:{tint};'
            f'border-color:{accent}66">{text}</span>')


def severity_pill(sev: Severity) -> str:
    return pill(sev.value, SEVERITY_TONE.get(sev, "neutral"))


def status_pill(status: ValidationStatus) -> str:
    return pill(status.value, STATUS_TONE.get(status, "neutral"))


def state_label(state: WorkflowState) -> str:
    """Readable name for a state; the underlying enum value is unchanged."""
    return STATE_LABEL.get(state, state.value.replace("_", " ").title())


def state_pill(state: WorkflowState) -> str:
    return pill(state_label(state), STATE_TONE.get(state, "neutral"))


def step_label(status: str) -> str:
    return STEP_LABEL.get(status, status.title())


def html(text: str) -> None:
    st.markdown(text, unsafe_allow_html=True)


def status_card(label: str, pill_html: str) -> None:
    """A metric-sized card holding a coloured status pill (sits next to st.metric cards)."""
    html(f'<div class="cm-status-card"><div class="cm-label">{label}</div>{pill_html}</div>')


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
