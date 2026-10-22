import streamlit as st

from codemind import config
from codemind.workspace import safe_join
from ui import components as ui


def render(orch) -> None:
    st.header("Upload & Project Explorer")
    st.caption("Uploaded code is only parsed, never executed during analysis. "
               f"Limits: {config.MAX_ZIP_BYTES // 1_000_000} MB archive, {config.MAX_FILES} files, "
               "no path traversal, no symlinks.")

    a, b = st.columns(2)
    with a:
        st.subheader("Bundled synthetic sample")
        st.write("A small 'student grades' app written for this demo, with planted, documented issues "
                 "and its own pytest suite.")
        if st.button("Load sample repository", key="load_sample", type="primary"):
            orch.load_sample()
            ui.flash_ok("Sample repository loaded. Run the analysis below.")
            st.rerun()
    with b:
        st.subheader("Upload a ZIP")
        up = st.file_uploader("Python project as .zip", type=["zip"], key="zip_upload")
        trusted = st.checkbox("I trust this code: allow running its tests (limited isolation, not a sandbox)",
                              key="trust_upload")
        if st.button("Ingest ZIP", key="ingest_zip", disabled=up is None):
            orch.load_zip(up.getvalue(), up.name, trusted=trusted)
            if orch.ctx.blocked_reason:
                ui.flash_error(orch.ctx.blocked_reason)
            else:
                ui.flash_ok(f"{up.name} ingested safely.")
            st.rerun()

    ctx = orch.ctx
    if ctx.snapshot is None:
        if ctx.blocked_reason:
            st.error(ctx.blocked_reason)
        return

    st.divider()
    snap = ctx.snapshot
    st.subheader(f"Repository: {snap.display_name}")
    if st.button("Run analysis (all agents)", key="run_analysis", type="primary",
                 disabled=ctx.state.value != "PLANNED"):
        with st.spinner("Agents working: understanding → risk analysis → baseline tests → advisor"):
            orch.analyze()
        b = ctx.baseline
        if ctx.blocked_reason:
            ui.flash_error(ctx.blocked_reason)
        elif b is not None and b.status.value in ("Not run", "Blocked"):
            ui.flash_error(f"Analysis finished with {len(ctx.findings)} findings, but the baseline tests "
                           f"produced no results: {b.checks[0].detail if b.checks else b.status.value}. "
                           "Details are on Validation Results.")
        else:
            ui.flash_ok(f"Analysis finished: {len(ctx.findings)} findings. See Findings & Explainability.")
        st.rerun()
    if ctx.state.value != "PLANNED":
        st.caption("Analysis already ran for this repository. Load it again to start a new run.")

    left, right = st.columns([2, 3])
    with left:
        st.markdown("**Directory tree**")
        st.code(snap.tree_text, language="text")
        skipped = [f for f in snap.files if f.skipped_reason]
        if skipped:
            st.markdown("**Skipped files**")
            st.dataframe([{"file": f.rel_path, "reason": f.skipped_reason} for f in skipped],
                         hide_index=True, width="stretch")
        if snap.ingest_warnings:
            st.warning("; ".join(snap.ingest_warnings))
    with right:
        readme = next((f.rel_path for f in snap.included_files if f.rel_path.lower() == "readme.md"), None)
        st.markdown("**README preview** (shown as text; links and images are not loaded)")
        if readme:
            text = safe_join(snap.root, readme).read_text(encoding="utf-8", errors="replace")
            st.code(text[:4000], language="markdown")
        else:
            st.write("No README.md at the repository root.")
        if ctx.summary:
            s = ctx.summary
            st.markdown("**Technologies detected:** " + (", ".join(s.technologies) or "none"))
            st.markdown("**Modules**")
            st.dataframe([{"file": m.path, "role": m.role, "functions": ", ".join(m.functions),
                           "entry point": "yes" if m.is_entry_point else ""} for m in s.modules],
                         hide_index=True, width="stretch")
            if s.doc_gaps:
                with st.expander(f"Documentation gaps ({len(s.doc_gaps)})"):
                    for g in s.doc_gaps:
                        st.write("- " + g)
            with st.expander("Evidence used for the summary"):
                for e in s.evidence:
                    st.caption(f"{e.file}:{e.line_start} - {e.note}")
                    st.code(e.snippet, language="text")
