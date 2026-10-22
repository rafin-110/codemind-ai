"""CodeMind AI - Streamlit entry point. Run with:  streamlit run app.py"""

from __future__ import annotations

from html import escape as html_escape

import streamlit as st

from codemind import config
from codemind.orchestrator.orchestrator import Orchestrator
from ui import components as ui
from ui.views import advisor, changes, findings, overview, upload, validation, workflow

st.set_page_config(page_title="CodeMind AI", layout="wide")
ui.inject_css()

if "orch" not in st.session_state:
    st.session_state.orch = Orchestrator(workspace_root=config.DEFAULT_WORKSPACE)
orch: Orchestrator = st.session_state.orch

# A new repository gets a new run id; selections from the previous run must not leak into it.
if st.session_state.get("_seen_run") != orch.ctx.run_id:
    for _stale in ("finding_pick", "advisor_pick"):
        st.session_state.pop(_stale, None)
    st.session_state["_seen_run"] = orch.ctx.run_id

PAGES = {
    "1. Overview": overview.render,
    "2. Upload & Explorer": upload.render,
    "3. Agent Workflow": workflow.render,
    "4. Findings & Explainability": findings.render,
    "5. Architecture Advisor": advisor.render,
    "6. Proposed Changes": changes.render,
    "7. Validation Results": validation.render,
}

with st.sidebar:
    ui.html('<p class="cm-brand">CodeMind AI</p><p class="cm-brand-sub">Agentic code review assistant: '
            'understand, debug and safely improve AI-generated code</p>')
    st.divider()
    if "nav" in st.session_state.get("goto", {}):
        st.session_state.page = st.session_state.pop("goto")["nav"]
    page = st.radio("Navigate", list(PAGES), key="page", label_visibility="collapsed")
    st.divider()
    ui.html('<div class="cm-side-card"><p class="cm-side-label">Workflow state</p>'
            + ui.state_pill(orch.ctx.state) + "</div>")
    if orch.ctx.snapshot:
        ui.html('<div class="cm-side-card"><p class="cm-side-label">Repository</p>'
                f'<span class="cm-side-value">{html_escape(orch.ctx.snapshot.display_name)}</span></div>')
    ui.html('<p class="cm-side-note">Original files are never modified. Nothing is committed or pushed.</p>')

ui.show_flash()
PAGES[page](orch)
