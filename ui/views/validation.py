import streamlit as st

from codemind.validation.report import build_json, build_markdown
from ui import components as ui


def render(orch) -> None:
    ctx = orch.ctx
    st.header("Validation Results")
    if ui.need_analysis(orch):
        return
    v = ctx.latest_validation
    if v is None:
        st.info("No patch has been validated yet.")
    else:
        p = next(x for x in ctx.proposals if x.patch_id == v.patch_id)
        ui.html("Status " + ui.status_pill(v.status))
        st.subheader(f"{v.patch_id}: {p.strategy_name} for {p.finding_id}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tests passed", v.tests_passed)
        c2.metric("Tests failed", v.tests_failed)
        c3.metric("Errors", v.tests_errors)
        c4.metric("Skipped", v.tests_skipped)
        st.dataframe([{"check": c.name, "status": c.status.value, "detail": c.detail,
                       "seconds": round(c.duration_s, 2)} for c in v.checks],
                     hide_index=True, width="stretch")
        bad = [c for c in v.test_cases if c.outcome in ("failed", "error")]
        if bad:
            st.markdown("**Failing tests**")
            for c in bad:
                with st.expander(f"{c.outcome.upper()}: {c.name}"):
                    st.code(c.message, language="text")
        if v.isolation_level:
            st.caption(f"Test isolation: {v.isolation_level}")
        st.markdown("**Limitations of this validation**")
        for lim in dict.fromkeys(v.limitations):
            st.write("- " + lim)
        if v.original_unchanged:
            st.success("Original files re-hashed after validation: unchanged.")
        with st.expander("Validation history"):
            for x in ctx.validations:
                st.write(f"- {x.patch_id}: {x.status.value} ({x.tests_passed} passed, {x.tests_failed} failed)")

    if ctx.baseline:
        b = ctx.baseline
        st.subheader("Baseline: tests on the untouched original")
        st.write(f"{b.tests_passed} passed, {b.tests_failed} failed, {b.tests_errors} errors, {b.tests_skipped} skipped. "
                 "Findings whose line appears in a failing test's traceback are marked Confirmed.")

    st.subheader("Download report")
    a, b = st.columns(2)
    a.download_button("JSON report", build_json(ctx), file_name=f"codemind_{ctx.run_id}.json",
                      mime="application/json", key="dl_json")
    b.download_button("Markdown report", build_markdown(ctx), file_name=f"codemind_{ctx.run_id}.md",
                      mime="text/markdown", key="dl_md")
