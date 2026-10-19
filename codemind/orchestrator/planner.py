"""Planner: builds a task plan from what the repository actually contains."""

from __future__ import annotations

from codemind.models import PlanStep, RepoSnapshot, TaskPlan


def build_plan(snapshot: RepoSnapshot, goal: str) -> TaskPlan:
    has_py = bool(snapshot.python_files)
    has_tests = any(f.rel_path.split("/")[-1].startswith("test_") or "/tests/" in f"/{f.rel_path}"
                    for f in snapshot.python_files)
    steps = [
        PlanStep("understand", "Repository Understanding Agent",
                 "Read README/metadata, map structure, entry points and dependencies"),
        PlanStep("analyze", "Bug & Risk Analysis Agent", "Run AST rules R000-R009 on Python sources",
                 enabled=has_py, reason="" if has_py else "no Python files: static analysis not applicable"),
        PlanStep("baseline", "Critic & Validation Agent",
                 "Run the repository's tests on an untouched copy to confirm findings by execution",
                 enabled=has_py and has_tests and snapshot.trusted,
                 reason=("" if has_py and has_tests and snapshot.trusted else
                         "no tests found" if not has_tests else
                         "untrusted upload: runtime tests disabled" if not snapshot.trusted else "no Python")),
        PlanStep("advise", "Solution & Architecture Advisor", "Compare current approach with alternatives",
                 enabled=has_py, reason="" if has_py else "nothing to compare without findings"),
        PlanStep("prioritize", "Planner / Orchestrator", "Rank findings by severity and confidence; pick next action",
                 enabled=has_py),
        PlanStep("propose", "Code Improvement Agent", "Propose a minimal patch for the finding you select",
                 enabled=has_py, reason="" if has_py else "no findings"),
        PlanStep("review", "Critic & Validation Agent", "Critique the proposal before it reaches you", enabled=has_py),
        PlanStep("approve", "Developer (human)", "Approve or reject the exact patch shown", enabled=has_py),
        PlanStep("validate", "Critic & Validation Agent",
                 "Apply to a working copy; syntax check, rule re-check, tests; retry up to 2 times", enabled=has_py),
    ]
    plan = TaskPlan(goal=goal, steps=steps)
    plan.step_status = {s.key: ("pending" if s.enabled else "skipped") for s in steps}
    return plan
