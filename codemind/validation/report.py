"""Downloadable run report (JSON and Markdown). Contains only recorded results."""

from __future__ import annotations

import json

from codemind.analysis.evidence import redact
from codemind.ingestion.zip_loader import rehash_snapshot
from codemind.models import WorkflowContext, to_jsonable, utc_now


def build_json(ctx: WorkflowContext) -> str:
    data = to_jsonable(ctx)
    if ctx.snapshot:
        data["snapshot"].pop("root", None)      # local path, not useful to readers
        data["original_unchanged_at_report_time"] = rehash_snapshot(ctx.snapshot) == ctx.snapshot.snapshot_hash
    # full file contents are not exported (they may contain secrets); the redacted diff is enough
    for prop in data.get("proposals", []):
        for e in prop.get("edits", []):
            e["new_content"] = f"<{len(e.pop('new_content'))} characters omitted; see unified_diff>"
    for v in data.get("validations", []) + ([data["baseline"]] if data.get("baseline") else []):
        v["raw_output_tail"] = redact(v.get("raw_output_tail", ""))
        for c in v.get("test_cases", []):
            c["message"] = redact(c.get("message", ""))
    data["generated_at"] = utc_now()
    data["notes"] = [
        "Findings come from deterministic AST rules; 'Potential' findings need human review.",
        "Validation results are recorded outputs of real checks; nothing in this report is simulated.",
        f"Explanation text source: {ctx.llm_label}.",
    ]
    return json.dumps(data, indent=2, ensure_ascii=False)


def build_markdown(ctx: WorkflowContext) -> str:
    snap, s = ctx.snapshot, ctx.summary
    out = [f"# CodeMind AI report: {s.title if s else (snap.display_name if snap else 'no repository')}", "",
           f"- Run: `{ctx.run_id}`  ", f"- Generated: {utc_now()}  ", f"- Final state: **{ctx.state.value}**  ",
           f"- Explanation text: {ctx.llm_label}"]
    if ctx.blocked_reason:
        out.append(f"- Blocked reason: {ctx.blocked_reason}")
    if snap:
        unchanged = rehash_snapshot(snap) == snap.snapshot_hash
        out += [f"- Source: {snap.source} ({snap.display_name}), {len(snap.included_files)} files analysed, "
                f"{len(snap.files) - len(snap.included_files)} skipped",
                f"- Original files unchanged: **{'yes' if unchanged else 'NO'}** (hash re-checked now)"]
    if s:
        out += ["", "## Repository summary", "", s.purpose, "",
                f"- Technologies: {', '.join(s.technologies) or 'none detected'}",
                f"- Entry points: {', '.join(s.entry_points) or 'none'}",
                f"- Dependencies: {', '.join(s.dependencies) or 'none declared'}"]
        if s.doc_gaps:
            out += ["", "### Documentation gaps", ""] + [f"- {g}" for g in s.doc_gaps]
    if ctx.baseline:
        b = ctx.baseline
        out += ["", "## Baseline tests on the original", "",
                f"{b.tests_passed} passed, {b.tests_failed} failed, {b.tests_errors} errors, "
                f"{b.tests_skipped} skipped ({b.isolation_level})."]
    out += ["", "## Findings", "", "| ID | Severity | Confidence | Rule | Location | Title |", "|---|---|---|---|---|---|"]
    for f in ctx.findings:
        out.append(f"| {f.id} | {f.severity.value} | {f.confidence.value} | {f.rule_id} | `{f.file}:{f.line}` | {f.title} |")
    for p in ctx.proposals:
        decision = next((a.decision for a in reversed(ctx.approvals) if a.patch_id == p.patch_id), "pending")
        v = next((v for v in ctx.validations if v.patch_id == p.patch_id), None)
        out += ["", f"## Proposal {p.patch_id} for {p.finding_id} (attempt {p.attempt})", "",
                f"- Strategy: {p.strategy_name}", f"- Human decision: **{decision}**",
                f"- Validation: **{v.status.value if v else 'not run'}**", "", "```diff", p.unified_diff.rstrip(), "```"]
        if v:
            out += ["", "| Check | Status | Detail |", "|---|---|---|"]
            out += [f"| {c.name} | {c.status.value} | {c.detail} |" for c in v.checks]
            if v.limitations:
                out += ["", "Limitations:"] + [f"- {lim}" for lim in dict.fromkeys(v.limitations)]
    out += ["", "## Decision log", ""] + [f"- `{d.at}` {d.from_state} → {d.to_state} ({d.event}): {d.reason}"
                                          for d in ctx.decisions]
    out += ["", "_Static findings are signals, not proof of bugs. Passing tests do not prove the absence of bugs._", ""]
    return "\n".join(out)
