"""Planner / Orchestrator: drives the agents through the state machine.

The UI only calls the public methods here. Each method checks the current state,
runs the right agent(s), passes structured outputs along, and records every
decision. Approval is the only way to reach patch application.
"""

from __future__ import annotations

from pathlib import Path

from codemind import config
from codemind.agents.bug_risk import BugRiskAgent
from codemind.agents.code_improvement import CodeImprovementAgent
from codemind.agents.critic_validator import CriticValidatorAgent
from codemind.agents.repo_understanding import RepositoryUnderstandingAgent
from codemind.agents.solution_advisor import SolutionAdvisorAgent
from codemind.ingestion.zip_loader import UnsafeArchiveError, ingest_zip, zip_directory
from codemind.llm.adapter import LLMAdapter, get_default_llm
from codemind.analysis.prioritizer import prioritize, renumber
from codemind.models import (
    AgentLogEntry, AnalysisStatus as A, CriticReview, PatchProposal, ValidationResult,
    ValidationStatus as V, WorkflowContext, WorkflowState as S, utc_now,
)
from codemind.orchestrator import states
from codemind.orchestrator.planner import ANALYSIS_STEPS, PATCH_CYCLE_STEPS, build_plan
from codemind.patching import approval as approval_mod
from codemind.patching.apply import PatchScopeError, apply_to_copy
from codemind.workspace import new_run_id, remove_tree

PLANNER = "Planner / Orchestrator"


class WorkflowError(RuntimeError):
    """A request that the workflow cannot honour in its current state (shown to the user)."""


class Orchestrator:
    def __init__(self, workspace_root: Path | None = None, llm: LLMAdapter | None = None) -> None:
        self.workspace_root = Path(workspace_root or config.DEFAULT_WORKSPACE)
        self.llm = llm or get_default_llm()
        self.repo_agent = RepositoryUnderstandingAgent()
        self.bug_agent = BugRiskAgent()
        self.advisor = SolutionAdvisorAgent(self.llm)
        self.improver = CodeImprovementAgent()
        self.critic = CriticValidatorAgent()
        self.ctx = WorkflowContext(run_id=new_run_id(), llm_label=self.llm.label)

    # ------------------------------------------------------------- helpers
    def _note(self, summary: str, outputs: tuple[str, ...] = (), error: str = "") -> None:
        now = utc_now()
        self.ctx.log.append(AgentLogEntry(PLANNER, now, now, self.ctx.state.value, self.ctx.state.value,
                                          summary, outputs, error))

    def _step(self, key: str, status: str) -> None:
        if self.ctx.plan and key in self.ctx.plan.step_status:
            self.ctx.plan.step_status[key] = status

    def _deps_done(self, key: str) -> tuple[bool, str]:
        step = next(s for s in self.ctx.plan.steps if s.key == key)
        missing = [d for d in step.depends_on if self.ctx.plan.step_status.get(d) != "done"]
        return not missing, ", ".join(f"{d} is {self.ctx.plan.step_status.get(d, 'missing')}" for d in missing)

    def _fail_safe(self, exc: Exception) -> None:
        reason = f"{type(exc).__name__}: {exc}"
        states.force_blocked(self.ctx, reason)
        self._note("Stopped safely after an unexpected error", (), reason)

    # ------------------------------------------------------------ ingestion
    def load_zip(self, data: bytes, name: str = "upload.zip", *, trusted: bool = False,
                 source: str = "zip") -> WorkflowContext:
        if self.ctx.snapshot is not None:          # previous run's files are no longer needed
            remove_tree(self.ctx.snapshot.root.parent)
        self.ctx = WorkflowContext(run_id=new_run_id(), llm_label=self.llm.label)
        run_dir = self.workspace_root / self.ctx.run_id
        try:
            self.ctx.snapshot = ingest_zip(data, run_dir, source=source, display_name=name, trusted=trusted)
        except UnsafeArchiveError as exc:
            self.ctx.blocked_reason = f"Archive rejected: {exc}"
            states.transition(self.ctx, "ingest_failed", self.ctx.blocked_reason)
            self._note("Ingestion rejected the archive; nothing was extracted", (), str(exc))
            return self.ctx
        snap = self.ctx.snapshot
        self.ctx.plan = build_plan(snap, self.ctx.goal)
        enabled = [s.key for s in self.ctx.plan.steps if s.enabled]
        skipped = [f"{s.key}: {s.reason}" for s in self.ctx.plan.steps if not s.enabled]
        states.transition(self.ctx, "plan_created",
                          f"{len(snap.included_files)} files accepted; plan: {', '.join(enabled)}")
        self._note(f"Plan created with {len(enabled)} active steps", tuple(skipped))
        return self.ctx

    def load_sample(self) -> WorkflowContext:
        data = zip_directory(config.SAMPLE_REPO_DIR)
        return self.load_zip(data, "student_grades_app.zip", trusted=True, source="sample")

    # ------------------------------------------------------------- analysis
    def analyze(self) -> WorkflowContext:
        """Run the analysis steps of the plan in order, honouring skipped steps and dependencies."""
        ctx = self.ctx
        if ctx.state is not S.PLANNED:
            raise WorkflowError(f"analysis needs a freshly loaded repository (state is {ctx.state.value})")
        current = ""
        try:
            states.transition(ctx, "analysis_started", "plan executed in order: " + ", ".join(
                k for k in ANALYSIS_STEPS if ctx.plan.step_status.get(k) == "pending"))
            for key in ANALYSIS_STEPS:
                if ctx.plan.step_status.get(key) != "pending":
                    continue                                   # disabled by the planner, reason is on the plan
                ok, why = self._deps_done(key)
                if not ok:
                    self._step(key, "skipped")
                    self._note(f"Skipped '{key}': dependency not satisfied ({why})")
                    continue
                current = key
                self._step(key, self._run_analysis_step(key))
            current = ""
            ran_rules = ctx.plan.step_status.get("analyze") == "done"
            ctx.analysis_status = A.COMPLETED if ran_rules else A.STRUCTURE_ONLY
            if not ran_rules:
                for key in PATCH_CYCLE_STEPS:
                    self._step(key, "skipped")
                decision = "no Python sources: structure-only report"
            else:
                top = ctx.findings[0] if ctx.findings else None
                decision = (f"{len(ctx.findings)} findings; suggested first: {top.id} ({top.severity.value}, "
                            f"{top.confidence.value}) {top.title}" if top
                            else "no rule matched; this is not proof of correctness")
                self._note(decision)
            states.transition(ctx, "analysis_complete", decision)
        except Exception as exc:  # fail safe, never pretend success
            if current:
                self._step(current, "failed")
            ctx.analysis_status = A.FAILED
            self._fail_safe(exc)
        return ctx

    def _run_analysis_step(self, key: str) -> str:
        """Run one analysis step; returns the plan status to record for it."""
        ctx = self.ctx
        if key == "understand":
            self.repo_agent.execute(ctx)
        elif key == "analyze":
            self.bug_agent.execute(ctx)
        elif key == "baseline":
            self.critic.execute(ctx, mode="baseline")
            # "done" only when tests really executed; otherwise show the step as failed, not as success
            ran = ctx.baseline is not None and ctx.baseline.status in (V.PASSED, V.FAILED)
            if not ran and ctx.baseline is not None:
                self._note(f"baseline tests produced no results ({ctx.baseline.status.value}): "
                           f"{ctx.baseline.checks[0].detail if ctx.baseline.checks else ''}")
            return "done" if ran else "failed"
        elif key == "prioritize":
            # re-rank after the baseline: executed tests may have upgraded findings to Confirmed
            ctx.findings = renumber(prioritize(ctx.findings))
            confirmed = sum(1 for f in ctx.findings if f.extra.get("confirmed_by"))
            self._note(f"Ranked {len(ctx.findings)} findings by severity and confidence "
                       f"({confirmed} confirmed by executed tests)")
        elif key == "advise":
            self.advisor.execute(ctx)
        else:
            raise WorkflowError(f"unknown analysis step {key}")
        return "done"

    # ------------------------------------------------------- patch proposal
    def select_finding(self, finding_id: str) -> WorkflowContext:
        ctx = self.ctx
        if ctx.analysis_status is not A.COMPLETED:
            raise WorkflowError(f"findings are not available: analysis is {ctx.analysis_status.value}")
        if ctx.snapshot is None or ctx.summary is None or ctx.finding(finding_id) is None:
            raise WorkflowError(f"unknown finding {finding_id}")
        if not states.can_transition(ctx.state, "finding_selected"):
            raise WorkflowError(f"cannot start a new proposal while in state {ctx.state.value}")
        ctx.selected_finding_id = finding_id
        ctx.retries = 0
        ctx.blocked_reason = ""
        for key in PATCH_CYCLE_STEPS:          # a new cycle: earlier results belong to another finding
            self._step(key, "pending")
        states.transition(ctx, "finding_selected", f"developer selected {finding_id}")
        try:
            self._propose_and_review(finding_id, feedback=None)
        except Exception as exc:
            self._fail_safe(exc)
        return ctx

    def _propose_and_review(self, finding_id: str, feedback: ValidationResult | None) -> None:
        ctx = self.ctx
        critique: CriticReview | None = None
        while True:
            out = self.improver.execute(ctx, finding_id=finding_id, feedback=feedback, critique=critique)
            if "no_fix" in out.outputs:
                self._step("propose", "failed")
                if not any(p.finding_id == finding_id for p in ctx.proposals):
                    states.transition(ctx, "no_fix_available", out.summary)
                else:
                    ctx.blocked_reason = f"No remaining fix strategy for {finding_id}; escalated to the developer."
                    states.transition(ctx, "no_strategy_left", ctx.blocked_reason)
                return
            self._step("propose", "done")
            proposal = ctx.current_proposal
            self.critic.execute(ctx, mode="review", proposal=proposal)
            review = ctx.reviews[proposal.patch_id]
            self._step("review", "done" if review.ok else "failed")
            if review.ok:
                states.transition(ctx, "critic_approved", f"{proposal.patch_id} passed critic review")
                self._step("approve", "pending")
                return
            ctx.retries += 1
            if ctx.retries > config.MAX_RETRIES:
                ctx.blocked_reason = "Critic rejected every proposal within the retry limit."
                states.transition(ctx, "critic_retries_exhausted", ctx.blocked_reason)
                return
            states.transition(ctx, "critic_rejected", "; ".join(review.issues))
            critique = review              # the next proposal is built knowing why this one was rejected

    # -------------------------------------------------------------- approval
    def _proposal(self, patch_id: str) -> PatchProposal:
        p = next((p for p in self.ctx.proposals if p.patch_id == patch_id), None)
        if p is None:
            raise approval_mod.ApprovalError(f"unknown proposal {patch_id}")
        return p

    def reject(self, patch_id: str, presented_hash: str, note: str = "") -> WorkflowContext:
        ctx = self.ctx
        proposal = self._proposal(patch_id)
        approval_mod.record(ctx, proposal, "rejected", presented_hash, note)
        states.transition(ctx, "human_rejected", f"developer rejected {patch_id}; original untouched, no copy made")
        self._step("approve", "done")
        return ctx

    def approve(self, patch_id: str, presented_hash: str, note: str = "") -> WorkflowContext:
        ctx = self.ctx
        proposal = self._proposal(patch_id)
        approval_mod.record(ctx, proposal, "approved", presented_hash, note)
        states.transition(ctx, "human_approved", f"developer approved {patch_id} (hash {proposal.patch_hash[:12]})")
        self._step("approve", "done")
        try:
            copy_root = apply_to_copy(ctx, proposal)
            self._note(f"Applied {patch_id} to working copy only", (str(copy_root),))
            states.transition(ctx, "validation_started", "patch applied to isolated working copy")
            self.critic.execute(ctx, mode="validate", proposal=proposal, copy_root=copy_root)
            vres = ctx.latest_validation
            self._step("validate", "failed" if vres is not None and vres.status in (V.BLOCKED, V.FAILED) else "done")
            self._after_validation(proposal)
        except (approval_mod.ApprovalError, PatchScopeError) as exc:
            states.force_blocked(ctx, f"Patch refused: {exc}")
        except Exception as exc:
            self._fail_safe(exc)
        return ctx

    def _after_validation(self, proposal: PatchProposal) -> None:
        ctx = self.ctx
        result = ctx.latest_validation
        if result.status is V.PASSED:
            states.transition(ctx, "validation_passed", "all checks passed")
        elif result.status is V.PARTIALLY_VERIFIED:
            states.transition(ctx, "validation_partial", "static checks passed; tests not run")
        elif result.status is V.BLOCKED:
            ctx.blocked_reason = next((c.detail for c in result.checks if c.status is V.BLOCKED), "validation blocked")
            states.transition(ctx, "validation_blocked", ctx.blocked_reason)
        else:
            states.transition(ctx, "validation_failed", "; ".join(
                f"{c.name}: {c.detail}" for c in result.checks if c.status is V.FAILED))
            ctx.retries += 1
            if ctx.retries > config.MAX_RETRIES:
                ctx.blocked_reason = (f"Validation failed {ctx.retries} times for {proposal.finding_id}; "
                                      "escalated to the developer.")
                states.transition(ctx, "retries_exhausted", ctx.blocked_reason)
                return
            states.transition(ctx, "retry_proposed",
                              f"retry {ctx.retries}/{config.MAX_RETRIES}: asking for a different strategy")
            self._propose_and_review(proposal.finding_id, feedback=result)

    def back_to_findings(self) -> WorkflowContext:
        if self.ctx.snapshot is None or self.ctx.summary is None:
            raise WorkflowError("nothing has been analysed yet")
        if self.ctx.analysis_status not in (A.COMPLETED, A.STRUCTURE_ONLY):
            raise WorkflowError(f"findings are not available: analysis is {self.ctx.analysis_status.value}")
        if not states.can_transition(self.ctx.state, "back_to_findings"):
            raise WorkflowError(f"cannot return to findings from {self.ctx.state.value}")
        states.transition(self.ctx, "back_to_findings", "developer returned to the findings list")
        return self.ctx
