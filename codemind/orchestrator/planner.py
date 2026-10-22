"""Planner: builds a task plan from what the repository actually contains.

Step order is execution order. `depends_on` lists the steps that must have finished
("done") before a step may run; the orchestrator enforces it.
"""

from __future__ import annotations

from codemind.models import PlanStep, RepoSnapshot, TaskPlan

ANALYSIS_STEPS = ("understand", "analyze", "baseline", "prioritize", "advise")
PATCH_CYCLE_STEPS = ("propose", "review", "approve", "validate")


def build_plan(snapshot: RepoSnapshot, goal: str) -> TaskPlan:
    has_py = bool(snapshot.python_files)
    has_tests = any(f.rel_path.split("/")[-1].startswith("test_") or "/tests/" in f"/{f.rel_path}"
                    for f in snapshot.python_files)
    steps = [
        PlanStep("understand", "Repository Understanding Agent",
                 "Read README/metadata, map structure, entry points and dependencies"),
        PlanStep("analyze", "Bug & Risk Analysis Agent", "Run AST rules R000-R009 on Python sources",
                 enabled=has_py, reason="" if has_py else "no Python files: static analysis not applicable",
                 depends_on=("understand",)),
        PlanStep("baseline", "Critic & Validation Agent",
                 "Run the repository's tests on an untouched copy to confirm findings by execution",
                 enabled=has_py and has_tests and snapshot.trusted,
                 reason=("" if has_py and has_tests and snapshot.trusted else
                         "no tests found" if not has_tests else
                         "untrusted upload: runtime tests disabled" if not snapshot.trusted else "no Python"),
                 depends_on=("analyze",)),
        # ranks after the baseline because executed tests can upgrade a finding to Confirmed
        PlanStep("prioritize", "Planner / Orchestrator", "Rank findings by severity and confidence; pick next action",
                 enabled=has_py, reason="" if has_py else "no findings to rank", depends_on=("analyze",)),
        PlanStep("advise", "Solution & Architecture Advisor", "Compare current approach with alternatives",
                 enabled=has_py, reason="" if has_py else "nothing to compare without findings",
                 depends_on=("analyze", "prioritize")),
        PlanStep("propose", "Code Improvement Agent", "Propose a minimal patch for the finding you select",
                 enabled=has_py, reason="" if has_py else "no findings", depends_on=("advise",)),
        PlanStep("review", "Critic & Validation Agent", "Critique the proposal before it reaches you",
                 enabled=has_py, depends_on=("propose",)),
        PlanStep("approve", "Developer (human)", "Approve or reject the exact patch shown",
                 enabled=has_py, depends_on=("review",)),
        PlanStep("validate", "Critic & Validation Agent",
                 "Apply to a working copy; syntax check, rule re-check, tests; retry up to 2 times",
                 enabled=has_py, depends_on=("approve",)),
    ]
    plan = TaskPlan(goal=goal, steps=steps)
    plan.step_status = {s.key: ("pending" if s.enabled else "skipped") for s in steps}
    return plan
