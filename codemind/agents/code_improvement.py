"""Agent 4: Code Improvement. Builds a minimal patch PROPOSAL for one finding.

Nothing is written to disk here. A proposal only becomes a change after the critic
review, an explicit human approval bound to its hash, and application to a copy.
"""

from __future__ import annotations

import ast

from codemind.agents.base import Agent, AgentOutput
from codemind.agents.repo_understanding import read_text
from codemind.models import (
    CriticReview, FileEdit, Finding, PatchProposal, ValidationResult, WorkflowContext, compute_patch_hash,
    sha256_bytes,
)
from codemind.analysis.evidence import redact
from codemind.patching.diff import unified_diff
from codemind.workspace import safe_join
from codemind.patching.fixers import STRATEGIES, NoFix, Strategy

SUGGESTED_TESTS = {
    "R001": ["normal input: `{symbol}([80, 90, 100])` returns the mean",
             "boundary: a single element", "invalid/boundary: empty input follows the chosen behaviour"],
    "R002": ["valid file still loads", "missing file still returns the fallback",
             "a programming error (e.g. TypeError) is no longer hidden"],
    "R003": ["valid literal input such as `[80, 90]` still works",
             "code-like input such as `__import__('os')` raises ValueError"],
    "R004": ["two calls without the argument return independent lists", "passing an explicit list still works"],
    "R005": ["a path containing spaces is passed as one argument", "no shell is started (shell=False)"],
    "R006": ["module imports without the variable set", "value is read from the environment when set"],
    "R007": ["existing lookups return the same rows", "a name containing a quote (O'Brien) works and cannot inject SQL"],
    "R009": ["existing behaviour for None and numbers is unchanged"],
}

RISKS = {
    "R001": ["Callers that relied on ZeroDivisionError (unlikely) see a different result/exception."],
    "R002": ["Errors other than OSError/ValueError now propagate to the caller (intended)."],
    "R003": ["Input that was valid Python *code* but not a literal is now rejected (intended)."],
    "R004": ["Code that relied on the shared default accumulating values changes behaviour (that was the bug)."],
    "R005": ["Commands relying on shell features (pipes, globbing, env expansion) would break."],
    "R006": ["The program now needs the environment variable set; the old value must be rotated."],
    "R007": ["None expected; results are identical for normal input."],
    "R009": ["None expected for plain values."],
}


class CodeImprovementAgent(Agent):
    name = "Code Improvement Agent"
    role = "Proposes a minimal patch with a diff, risks and suggested tests."

    def run(self, ctx: WorkflowContext, *, finding_id: str, feedback: ValidationResult | None = None,
            critique: CriticReview | None = None, exclude: set[int] | None = None, **_) -> AgentOutput:
        f = ctx.finding(finding_id)
        if f is None:
            raise ValueError(f"unknown finding {finding_id}")
        strategies = STRATEGIES.get(f.rule_id, [])
        if not strategies:
            return AgentOutput(f"No automatic fix for {f.rule_id}; manual remediation: {f.remediation}",
                               ["no_fix"])
        tried = set(exclude or ())
        tried |= {p.strategy_index for p in ctx.proposals if p.finding_id == f.id}
        order = self.order_strategies(strategies, tried, feedback, critique)
        source = read_text(ctx.snapshot, f.file)
        reasons = []
        for idx in order:
            strat = strategies[idx]
            try:
                new_source = strat.apply(source, f)
                ast.parse(new_source)
            except (NoFix, SyntaxError, ValueError) as exc:
                reasons.append(f"{strat.name}: {exc}")
                continue
            proposal = self._proposal(ctx, f, idx, strat, source, new_source, feedback, critique)
            ctx.proposals.append(proposal)
            why = ""
            if critique is not None:
                why = f" (chosen after critic rejected {critique.patch_id})"
            elif feedback is not None:
                why = f" (chosen after validation feedback on attempt {proposal.attempt - 1})"
            return AgentOutput(f"Proposed '{strat.name}' for {f.id}{why}.",
                               [f"patch {proposal.patch_id}", f"{len(proposal.unified_diff.splitlines())} diff lines"]
                               + proposal.context_used)
        return AgentOutput(f"No remaining fix strategy for {f.id}.", ["no_fix"] + reasons)

    @staticmethod
    def order_strategies(strategies: list[Strategy], tried: set[int], feedback: ValidationResult | None,
                         critique: CriticReview | None = None) -> list[int]:
        remaining = [i for i in range(len(strategies)) if i not in tried]
        if feedback is None and critique is None:
            return remaining
        text = " ".join(critique.issues) if critique else ""
        if feedback is not None:
            text += " " + feedback.raw_output_tail + " " + " ".join(c.message for c in feedback.test_cases)
        text = text.lower()
        # strategies whose keywords appear in the failing test output / critic issues go first
        scored = sorted(remaining, key=lambda i: -sum(k in text for k in strategies[i].feedback_keywords))
        return scored

    @staticmethod
    def _proposal(ctx, f: Finding, idx: int, strat: Strategy, before: str, after: str, feedback,
                  critique: CriticReview | None = None) -> PatchProposal:
        file_info = next(fi for fi in ctx.snapshot.included_files if fi.rel_path == f.file)
        edits = [FileEdit(f.file, file_info.sha256, after)]
        base = ctx.snapshot.snapshot_hash
        attempt = 1 + sum(1 for p in ctx.proposals if p.finding_id == f.id)
        patch_hash = compute_patch_hash(edits, base)
        symbol = f.symbol or "module"
        root_cause = f"{f.title} at {f.file}:{f.line}: {f.extra.get('detail', '')}. {f.why_problematic}"
        if feedback is not None:
            failed = [c.name for c in feedback.test_cases if c.outcome in ("failed", "error")]
            root_cause += f" Previous attempt failed validation ({', '.join(failed) or feedback.status.value})."
        return PatchProposal(
            patch_id=f"P-{f.id[2:]}-{attempt}-{patch_hash[:6]}",
            finding_id=f.id, strategy_index=idx, strategy_name=strat.name,
            root_cause=root_cause, intended_behaviour=strat.description,
            edits=edits, unified_diff=redact(unified_diff(f.file, before, after)),
            affected_files=[f.file], regression_risks=RISKS.get(f.rule_id, []),
            suggested_tests=[t.format(symbol=symbol) for t in SUGGESTED_TESTS.get(f.rule_id, [])],
            base_snapshot_hash=base, patch_hash=patch_hash, attempt=attempt,
            context_used=handoff_notes(ctx, f, feedback, critique),
        )


def handoff_notes(ctx: WorkflowContext, f: Finding, feedback: ValidationResult | None,
                  critique: CriticReview | None) -> list[str]:
    """What this proposal was built from, taken from earlier agents' outputs on the shared context."""
    notes = [f"finding evidence: {f.evidence.file}:{f.evidence.line_start}-{f.evidence.line_end}"]
    if f.extra.get("confirmed_by"):
        notes.append(f"baseline: confirmed by failing test(s) {', '.join(f.extra['confirmed_by'])}")
    rec = ctx.recommendations.get(f.id)
    if rec is not None:
        notes.append(f"advisor recommended: {rec.recommended}")
        if rec.keep_current:
            notes.append("advisor: current approach is acceptable; this patch is optional")
    if critique is not None:
        notes.append(f"critic rejected {critique.patch_id}: {'; '.join(critique.issues) or 'no reason given'}")
    if feedback is not None:
        failed = [c.name for c in feedback.test_cases if c.outcome in ("failed", "error")]
        notes.append(f"validation of {feedback.patch_id} was {feedback.status.value}"
                     + (f": {', '.join(failed)}" if failed else ""))
    return notes


def source_hash_matches(ctx: WorkflowContext, proposal: PatchProposal) -> bool:
    """True when every edited file in the original still has the hash the proposal was built from."""
    for e in proposal.edits:
        if sha256_bytes(safe_join(ctx.snapshot.root, e.rel_path).read_bytes()) != e.original_sha256:
            return False
    return True
