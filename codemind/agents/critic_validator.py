"""Agent 5: Critic & Validation.

* `baseline`  - runs the repo's tests on an untouched copy (trusted repos only) and
                marks findings Confirmed when a failing test points at their line.
* `review`    - critiques a proposal BEFORE approval (scope, syntax, does it remove the finding?).
* `validate`  - checks an APPLIED patch on the working copy with real tools and reports
                Passed / Failed / Not run / Blocked / Partially verified honestly.
"""

from __future__ import annotations

import ast

from codemind.agents.base import Agent, AgentOutput
from codemind.analysis import ast_rules
from codemind.ingestion.zip_loader import rehash_snapshot
from codemind.models import (
    CheckResult, Confidence, CriticReview, PatchProposal, TestCaseResult, ValidationResult,
    ValidationStatus as V, WorkflowContext,
)
from codemind.patching.diff import changed_line_count
from codemind.validation import sandbox_runner
from codemind.validation.syntax_check import check_files
from codemind.workspace import make_working_copy, safe_join

MAX_CHANGED_LINES = 16


def _rule_hits(source: str, rule_id: str, symbol: str) -> int | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    return sum(1 for h in ast_rules.run_rules(tree) if h.rule_id == rule_id and h.symbol == symbol)


def tests_allowed(ctx: WorkflowContext) -> tuple[bool, str]:
    if not ctx.snapshot.trusted:
        return False, ("Runtime tests are disabled for untrusted uploads. Tick 'I trust this code' to "
                       "run them with limited isolation.")
    if not (ctx.summary and ctx.summary.has_tests):
        return False, "The repository has no tests, so runtime behaviour could not be checked."
    return True, ""


class CriticValidatorAgent(Agent):
    name = "Critic & Validation Agent"
    role = "Reviews proposals, runs real checks on the working copy, and reports outcomes honestly."

    def run(self, ctx: WorkflowContext, *, mode: str, proposal: PatchProposal | None = None, **kw) -> AgentOutput:
        if mode == "baseline":
            return self._baseline(ctx)
        if mode == "review":
            return self._review(ctx, proposal)
        if mode == "validate":
            return self._validate(ctx, proposal, kw["copy_root"])
        raise ValueError(mode)

    # ---------------------------------------------------------------- baseline
    def _baseline(self, ctx: WorkflowContext) -> AgentOutput:
        allowed, why = tests_allowed(ctx)
        if not allowed:
            return AgentOutput(f"Baseline tests not run: {why}", ["baseline: Not run"])
        copy_root = make_working_copy(ctx.snapshot, "baseline")
        out = sandbox_runner.run_pytest(copy_root)
        status = (V.BLOCKED if out.timed_out else V.NOT_RUN if not out.ran
                  else V.PASSED if out.failed + out.errors == 0 else V.FAILED)
        ctx.baseline = ValidationResult("baseline", status, [], out.passed, out.failed, out.errors, out.skipped,
                                        out.cases, out.output_tail, out.isolation_level, out.limitations,
                                        working_copy=str(copy_root))
        confirmed = []
        for f in ctx.findings:
            # pytest prints OS-native paths (grades\stats.py on Windows), finding paths are POSIX
            linked = [c.name for c in out.cases if c.outcome in ("failed", "error")
                      and f"{f.file}:{f.line}" in c.message.replace("\\", "/")]
            if linked:
                f.confidence = Confidence.CONFIRMED
                f.verification = V.FAILED
                f.extra["confirmed_by"] = linked
                confirmed.append(f"{f.id} confirmed by {', '.join(linked)}")
        return AgentOutput(
            f"Baseline on original: {out.passed} passed, {out.failed} failed, {out.errors} errors "
            f"({out.duration_s:.1f}s); {len(confirmed)} finding(s) confirmed by execution.", confirmed)

    # ------------------------------------------------------------------ review
    def review(self, ctx: WorkflowContext, proposal: PatchProposal) -> CriticReview:
        f = ctx.finding(proposal.finding_id)
        issues: list[str] = []
        known = {fi.rel_path: fi for fi in ctx.snapshot.included_files}
        in_scope = True
        for e in proposal.edits:
            if e.rel_path != f.file:
                in_scope = False
                issues.append(f"edits '{e.rel_path}' but the finding is in '{f.file}'")
            if e.rel_path not in known:
                in_scope = False
                issues.append(f"'{e.rel_path}' is not an existing analysed file")
            else:
                try:
                    safe_join(ctx.snapshot.root, e.rel_path)
                except ValueError as exc:
                    in_scope = False
                    issues.append(str(exc))
                if known[e.rel_path].sha256 != e.original_sha256:
                    issues.append(f"'{e.rel_path}' was built from a different version of the file")
        if changed_line_count(proposal.unified_diff) > MAX_CHANGED_LINES:
            issues.append(f"patch changes more than {MAX_CHANGED_LINES} lines; not a minimal fix")
        addresses = False
        edit = next((e for e in proposal.edits if e.rel_path == f.file), None)
        if edit is not None:
            try:
                compile(edit.new_content, edit.rel_path, "exec", dont_inherit=True)
            except SyntaxError as exc:
                issues.append(f"patched file does not compile: line {exc.lineno}: {exc.msg}")
            before = _rule_hits((ctx.snapshot.root / f.file).read_text(encoding="utf-8"), f.rule_id, f.symbol)
            after = _rule_hits(edit.new_content, f.rule_id, f.symbol)
            addresses = before is not None and after is not None and after < before
            if not addresses:
                issues.append(f"rule {f.rule_id} still matches in `{f.symbol or 'module'}` after the patch")
        review = CriticReview(proposal.patch_id, in_scope, addresses, issues)
        ctx.reviews[proposal.patch_id] = review
        return review

    def _review(self, ctx, proposal) -> AgentOutput:
        r = self.review(ctx, proposal)
        verdict = "accepted for human review" if r.ok else "sent back to the Code Improvement Agent"
        return AgentOutput(f"Reviewed {proposal.patch_id}: {verdict}.", r.issues or ["scope ok", "finding removed by rule re-check"])

    # ---------------------------------------------------------------- validate
    def validate(self, ctx: WorkflowContext, proposal: PatchProposal, copy_root) -> ValidationResult:
        f = ctx.finding(proposal.finding_id)
        checks: list[CheckResult] = []
        files = [e.rel_path for e in proposal.edits]

        syntax = check_files(copy_root, files)
        checks.append(syntax)

        patched = (copy_root / f.file).read_text(encoding="utf-8")
        before = _rule_hits((ctx.snapshot.root / f.file).read_text(encoding="utf-8"), f.rule_id, f.symbol)
        after = _rule_hits(patched, f.rule_id, f.symbol)
        recheck_ok = before is not None and after is not None and after < before
        checks.append(CheckResult("Finding re-check", V.PASSED if recheck_ok else V.FAILED,
                                  f"rule {f.rule_id} matches in `{f.symbol or 'module'}`: before {before}, after {after}"))

        result = ValidationResult(proposal.patch_id, V.NOT_RUN, checks, working_copy=str(copy_root))
        allowed, why = tests_allowed(ctx)
        if syntax.status is V.FAILED:
            checks.append(CheckResult("Tests", V.NOT_RUN, "skipped because the syntax check failed"))
            result.status = V.FAILED
        elif not allowed:
            checks.append(CheckResult("Tests", V.NOT_RUN, why))
            result.limitations.append(why)
            result.status = V.PARTIALLY_VERIFIED if recheck_ok else V.FAILED
        else:
            self._run_tests(ctx, f, result, copy_root, recheck_ok)

        unchanged = rehash_snapshot(ctx.snapshot) == ctx.snapshot.snapshot_hash
        result.original_unchanged = unchanged
        checks.append(CheckResult("Original unchanged", V.PASSED if unchanged else V.FAILED,
                                  "re-hashed original matches the ingest hash" if unchanged
                                  else "ORIGINAL FILES CHANGED - investigate"))
        if not unchanged:
            result.status = V.BLOCKED
        result.limitations.append("Passing tests and static checks do not prove the code is bug-free.")
        ctx.validations.append(result)
        return result

    def _run_tests(self, ctx, f, result: ValidationResult, copy_root, recheck_ok: bool) -> None:
        out = sandbox_runner.run_pytest(copy_root)
        result.tests_passed, result.tests_failed = out.passed, out.failed
        result.tests_errors, result.tests_skipped = out.errors, out.skipped
        result.test_cases, result.raw_output_tail = out.cases, out.output_tail
        result.isolation_level = out.isolation_level
        result.limitations += out.limitations
        if out.timed_out:
            result.checks.append(CheckResult("Tests", V.BLOCKED, out.note, out.duration_s))
            result.status = V.BLOCKED
            return
        if not out.ran:
            result.checks.append(CheckResult("Tests", V.NOT_RUN, out.note, out.duration_s))
            result.status = V.PARTIALLY_VERIFIED if recheck_ok else V.FAILED
            return
        if out.total == 0:
            result.checks.append(CheckResult("Tests", V.NOT_RUN, out.note or "no tests collected", out.duration_s))
            result.status = V.PARTIALLY_VERIFIED if recheck_ok else V.FAILED
            return

        bad = {c.name for c in out.cases if c.outcome in ("failed", "error")}
        base_cases = {c.name: c.outcome for c in (ctx.baseline.test_cases if ctx.baseline else [])}
        regressions = sorted(n for n in bad if base_cases.get(n) == "passed" or n not in base_cases)
        linked = set(f.extra.get("confirmed_by", []))
        still_failing_linked = sorted(bad & linked)
        fixed_linked = sorted(linked - bad)
        pre_existing = sorted(bad - set(regressions) - linked)

        parts = [f"{out.passed} passed, {out.failed} failed, {out.errors} errors, {out.skipped} skipped"]
        if fixed_linked:
            parts.append(f"now passing (were failing because of this finding): {', '.join(fixed_linked)}")
        if still_failing_linked:
            parts.append(f"still failing, linked to this finding: {', '.join(still_failing_linked)}")
        if regressions:
            parts.append(f"REGRESSIONS: {', '.join(regressions)}")
        if pre_existing:
            parts.append(f"pre-existing failures unrelated to this patch: {', '.join(pre_existing)}")
            result.limitations.append(f"{len(pre_existing)} test(s) were already failing before this patch.")
        ok = not regressions and not still_failing_linked
        result.checks.append(CheckResult("Tests", V.PASSED if ok else V.FAILED, "; ".join(parts), out.duration_s))
        result.status = V.PASSED if ok and recheck_ok else V.FAILED
        if result.status is V.PASSED and fixed_linked:
            f.verification = V.PASSED

    def _validate(self, ctx, proposal, copy_root) -> AgentOutput:
        r = self.validate(ctx, proposal, copy_root)
        return AgentOutput(
            f"Validated {proposal.patch_id}: {r.status.value} "
            f"(tests: {r.tests_passed} passed, {r.tests_failed} failed, {r.tests_errors} errors).",
            [f"{c.name}: {c.status.value} - {c.detail}" for c in r.checks])


def failure_feedback(result: ValidationResult) -> list[TestCaseResult]:
    return [c for c in result.test_cases if c.outcome in ("failed", "error")]
