"""Agent 3: Solution & Architecture Advisor.

Compares the current approach with alternatives for each finding, using the curated
knowledge base plus project facts gathered by Agents 1 and 2. It also produces
project-level observations and says explicitly when the current approach is fine.
"""

from __future__ import annotations

from codemind.agents.base import Agent, AgentOutput
from codemind.analysis.advisor_kb import KB
from codemind.llm.adapter import LLMAdapter, get_default_llm
from codemind.models import Finding, Recommendation, Severity, WorkflowContext


class SolutionAdvisorAgent(Agent):
    name = "Solution & Architecture Advisor"
    role = "Compares current vs. alternative approaches and explains trade-offs."

    def __init__(self, llm: LLMAdapter | None = None) -> None:
        self.llm = llm or get_default_llm()

    def run(self, ctx: WorkflowContext, **_) -> AgentOutput:
        has_tests = bool(ctx.summary and ctx.summary.has_tests)
        recs: dict[str, Recommendation] = {}
        keep = 0
        for f in ctx.findings:
            rec = self.recommend(f, has_tests)
            keep += rec.keep_current
            recs[f.id] = rec
        ctx.recommendations = recs
        return AgentOutput(
            f"{len(recs)} comparisons written; {keep} recommend keeping the current approach.",
            [f"text source: {self.llm.label}"],
        )

    def recommend(self, f: Finding, has_tests: bool) -> Recommendation:
        kb = KB.get(f.rule_id)
        if kb is None:
            return Recommendation(f.id, "Not covered by the knowledge base.", [], "Manual review", "", [],
                                  "Review manually", keep_current=True)
        fields = {"symbol": f.symbol or "module", "denominator": f.extra.get("denominator", "the value"),
                  "name": f.extra.get("name", "the value")}
        current = kb["current"].format(**fields)
        assumptions = [f"Finding confidence is '{f.confidence.value}': "
                       + ("treat as a strong signal." if f.confidence.rank >= 2 else "confirm the risk before changing code.")]
        if f.extra.get("confirmed_by"):
            assumptions.append("Confirmed by executing the repository's tests: failing "
                               + ", ".join(f.extra["confirmed_by"]) + ".")
        if has_tests:
            assumptions.append("The repository has tests, so a change can be validated by running them.")
        else:
            assumptions.append("No tests were found: any change can only be checked statically.")

        keep_current = False
        next_action = "Select this finding and ask the Code Improvement Agent for a proposal."
        if f.rule_id == "R009" and f.severity is Severity.LOW:
            keep_current = True
            next_action = ("Optional: current code is acceptable for plain numbers; fix only if you want "
                           "lint-clean code.")
        if f.rule_id == "R008":
            next_action = "Apply the recommended pattern manually; no automatic patch is offered for interactive input."
        if f.rule_id == "R006":
            assumptions.append("If the value was a real credential it is already exposed and must be rotated.")

        # the model only rewords; it is grounded in the finding's own evidence and never decides anything
        rationale = self.llm.rephrase(kb["rationale"], context=(
            f"{f.title} ({f.severity.value}, {f.confidence.value}) at {f.file}:{f.line}\n"
            f"Evidence:\n{f.evidence.snippet}"))
        return Recommendation(
            finding_id=f.id, current_approach=current, alternatives=list(kb["alternatives"]),
            recommended=kb["recommended"], rationale=rationale.text, assumptions=assumptions,
            next_action=next_action, keep_current=keep_current, text_origin=rationale.origin,
        )
