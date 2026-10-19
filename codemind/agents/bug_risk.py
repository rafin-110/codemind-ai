"""Agent 2: Bug and Risk Analysis. Runs the AST rules (and pyflakes if installed)."""

from __future__ import annotations

from codemind.agents.base import Agent, AgentOutput
from codemind.agents.repo_understanding import parse_all_python
from codemind.analysis import ast_rules
from codemind.analysis.evidence import make_evidence
from codemind.analysis.prioritizer import prioritize, renumber, severity_counts
from codemind.models import Finding, ValidationStatus, WorkflowContext


class BugRiskAgent(Agent):
    name = "Bug & Risk Analysis Agent"
    role = "Finds explainable risks with evidence; separates likely issues from potential ones."

    def run(self, ctx: WorkflowContext, **_) -> AgentOutput:
        snap = ctx.snapshot
        assert snap is not None
        findings: list[Finding] = []
        errors: list[str] = []
        pyflakes_used = False
        test_modules = {m.path for m in (ctx.summary.modules if ctx.summary else []) if m.is_test}

        for mod in parse_all_python(snap):
            if mod.error is not None:
                line = mod.error.lineno or 1
                findings.append(self._finding("R000", mod.path, mod.source, line, line, "",
                                              f"SyntaxError: {mod.error.msg}"))
                continue
            if mod.path in test_modules:
                continue  # test code is evidence, not a target for findings
            try:
                hits = ast_rules.run_rules(mod.tree)
            except Exception as exc:  # a rule crash must not stop the whole analysis
                errors.append(f"{mod.path}: {type(exc).__name__}: {exc}")
                continue
            extra = ast_rules.run_pyflakes(mod.path, mod.source)
            if extra is not None:
                pyflakes_used = True
                hits += extra
            for h in hits:
                findings.append(self._finding(h.rule_id, mod.path, mod.source, h.line, h.end_line, h.symbol,
                                              h.detail, h.severity, h.confidence, h.extra,
                                              source="pyflakes" if h.rule_id.startswith("PF") else "ast-rule"))

        ctx.findings = renumber(prioritize(findings))
        counts = severity_counts(ctx.findings)
        outputs = [f"{k}: {v}" for k, v in counts.items()]
        outputs.append("pyflakes: used" if pyflakes_used else "pyflakes: not installed (optional)")
        outputs += [f"rule error: {e}" for e in errors]
        return AgentOutput(f"{len(ctx.findings)} findings across {len(snap.python_files)} Python files "
                           f"(rules R000-R009{', PF01' if pyflakes_used else ''}).", outputs)

    @staticmethod
    def _finding(rule_id, path, code, line, end_line, symbol, detail, severity=None, confidence=None,
                 extra=None, source="ast-rule") -> Finding:
        info = ast_rules.RULES[rule_id]
        title = info.title + (f" in `{symbol}()`" if symbol else "")
        return Finding(
            id="", rule_id=rule_id, title=title, category=info.category,
            severity=severity or info.severity, confidence=confidence or info.confidence,
            file=path, line=line,
            evidence=make_evidence(path, code, line, end_line, note=detail, context=2),
            why_problematic=info.why, impact=info.impact, remediation=info.remediation,
            validation_method=info.validation,
            verification=ValidationStatus.NOT_RUN if rule_id != "R000" else ValidationStatus.FAILED,
            source=source, symbol=symbol, extra=dict(extra or {}, detail=detail),
        )
