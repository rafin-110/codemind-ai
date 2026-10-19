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
from codemind.models import (
    AgentLogEntry, PatchProposal, ValidationResult, ValidationStatus as V, WorkflowContext,
    WorkflowState as S, utc_now,
)
from codemind.orchestrator import states
from codemind.orchestrator.planner import build_plan
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
        ctx = self.ctx
        if ctx.state is not S.PLANNED:
            raise WorkflowError(f"analysis needs a freshly loaded repository (state is {ctx.state.value})")
        try:
            states.transition(ctx, "analysis_started", "plan executed in order: understanding first")
            self.repo_agent.execute(ctx)
            self._step("understand", "done")
            if not ctx.snapshot.python_files:
                for key in ("analyze", "baseline", "advise", "prioritize", "propose", "review", "approve", "validate"):
                    self._step(key, "skipped")
                ctx.analysis_status = V.NOT_RUN
                states.transition(ctx, "analysis_complete", "no Python sources: structure-only report")
                return ctx
            self.bug_agent.execute(ctx)
            self._step("analyze", "done")
            if ctx.plan.step_status.get("baseline") == "pending":
                self.critic.execute(ctx, mode="baseline")
                self._step("baseline", "done")
            self.advisor.execute(ctx)
            self._step("advise", "done")
            self._step("prioritize", "done")
            ctx.analysis_status = V.PASSED
            top = ctx.findings[0] if ctx.findings else None
            decision = (f"{len(ctx.findings)} findings; suggested first: {top.id} ({top.severity.value}, "
                        f"{top.confidence.value}) {top.title}" if top else "no rule matched; this is not proof of correctness")
            self._note(decision)
            states.transition(ctx, "analysis_complete", decision)
        except Exception as exc:  # fail safe, never pretend success
            self._fail_safe(exc)
        return ctx

    # ------------------------------------------------------- patch proposal
    def select_finding(self, finding_id: str) -> WorkflowContext:
        ctx = self.ctx
        if ctx.snapshot is None or ctx.summary is None or ctx.finding(finding_id) is None:
            raise WorkflowError(f"unknown finding {finding_id}")
        if not states.can_transition(ctx.state, "finding_selected"):
            raise WorkflowError(f"cannot start a new proposal while in state {ctx.state.value}")
        ctx.selected_finding_id = finding_id
        ctx.retries = 0
        ctx.blocked_reason = ""
        states.transition(ctx, "finding_selected", f"developer selected {finding_id}")
        try:
            self._propose_and_review(finding_id, feedback=None)
        except Exception as exc:
            self._fail_safe(exc)
        return ctx

    def _propose_and_review(self, finding_id: str, feedback: ValidationResult | None) -> None:
        ctx = self.ctx
        while True:
            out = self.improver.execute(ctx, finding_id=finding_id, feedback=feedback)
            self._step("propose", "done")
            if "no_fix" in out.outputs:
                if not any(p.finding_id == finding_id for p in ctx.proposals):
                    states.transition(ctx, "no_fix_available", out.summary)
                else:
                    ctx.blocked_reason = f"No remaining fix strategy for {finding_id}; escalated to the developer."
                    states.transition(ctx, "no_strategy_left", ctx.blocked_reason)
                return
            proposal = ctx.current_proposal
            self.critic.execute(ctx, mode="review", proposal=proposal)
            self._step("review", "done")
            review = ctx.reviews[proposal.patch_id]
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
            self._step("validate", "done")
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
        if not states.can_transition(self.ctx.state, "back_to_findings"):
            raise WorkflowError(f"cannot return to findings from {self.ctx.state.value}")
        states.transition(self.ctx, "back_to_findings", "developer returned to the findings list")
        return self.ctx
