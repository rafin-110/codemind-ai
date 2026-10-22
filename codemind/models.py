"""Typed data structures shared by every agent (ARCHITECTURE.md section 6).

Agents never pass free-form text to each other; they read and write these
dataclasses on a single `WorkflowContext`.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


class Severity(str, enum.Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFO = "Info"

    @property
    def rank(self) -> int:
        return {"Critical": 5, "High": 4, "Medium": 3, "Low": 2, "Info": 1}[self.value]


class Confidence(str, enum.Enum):
    CONFIRMED = "Confirmed"   # reproduced by an executed test or by the parser itself
    LIKELY = "Likely"         # strong syntactic pattern
    POTENTIAL = "Potential"   # needs human review

    @property
    def rank(self) -> int:
        return {"Confirmed": 3, "Likely": 2, "Potential": 1}[self.value]


class ValidationStatus(str, enum.Enum):
    PASSED = "Passed"
    FAILED = "Failed"
    NOT_RUN = "Not run"
    BLOCKED = "Blocked"
    PARTIALLY_VERIFIED = "Partially verified"


class AnalysisStatus(str, enum.Enum):
    """Whether the analysis *ran*. Says nothing about whether the code is correct;
    test outcomes live in `ValidationResult`, never here."""
    NOT_STARTED = "Not started"
    COMPLETED = "Completed"
    STRUCTURE_ONLY = "Completed (structure only)"   # no Python: static rules not applicable
    FAILED = "Failed"


class WorkflowState(str, enum.Enum):
    RECEIVED = "RECEIVED"
    PLANNED = "PLANNED"
    ANALYZING = "ANALYZING"
    FINDINGS_READY = "FINDINGS_READY"
    PATCH_PROPOSED = "PATCH_PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    PATCH_APPLIED_TO_COPY = "PATCH_APPLIED_TO_COPY"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    BLOCKED = "BLOCKED"


# --------------------------------------------------------------------------- repo

@dataclass(frozen=True)
class FileInfo:
    rel_path: str
    size: int
    language: str
    sha256: str | None = None
    skipped_reason: str | None = None   # None means the file is analysable


@dataclass
class RepoSnapshot:
    snapshot_id: str
    source: str                 # "zip" | "sample" | "github"
    root: Path                  # read-only original copy
    files: list[FileInfo]
    tree_text: str
    snapshot_hash: str
    display_name: str = ""
    ingest_warnings: list[str] = field(default_factory=list)
    trusted: bool = False       # True only for the bundled sample or explicit opt-in

    @property
    def included_files(self) -> list[FileInfo]:
        return [f for f in self.files if f.skipped_reason is None]

    @property
    def python_files(self) -> list[FileInfo]:
        return [f for f in self.included_files if f.rel_path.endswith(".py")]


@dataclass(frozen=True)
class Evidence:
    file: str
    line_start: int
    line_end: int
    snippet: str
    note: str = ""


@dataclass(frozen=True)
class ModuleInfo:
    path: str
    role: str
    functions: tuple[str, ...] = ()
    classes: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()
    is_entry_point: bool = False
    is_test: bool = False
    docstring: str = ""


@dataclass
class RepoSummary:
    title: str
    purpose: str
    technologies: list[str]
    entry_points: list[str]
    modules: list[ModuleInfo]
    dependencies: list[str]
    import_graph: dict[str, list[str]]
    doc_gaps: list[str]
    evidence: list[Evidence]
    readme_sections: list[str] = field(default_factory=list)
    has_tests: bool = False


# ----------------------------------------------------------------------- findings

@dataclass
class Finding:
    id: str
    rule_id: str
    title: str
    category: str
    severity: Severity
    confidence: Confidence
    file: str
    line: int
    evidence: Evidence
    why_problematic: str
    impact: str
    remediation: str
    validation_method: str
    verification: ValidationStatus = ValidationStatus.NOT_RUN
    source: str = "ast-rule"
    symbol: str = ""          # enclosing function, if any
    extra: dict[str, Any] = field(default_factory=dict)  # rule-specific data for fixers

    @property
    def priority(self) -> tuple[int, int]:
        return (self.severity.rank, self.confidence.rank)


@dataclass(frozen=True)
class Alternative:
    name: str
    pros: tuple[str, ...]
    cons: tuple[str, ...]
    cost: str
    complexity: str
    maintainability: str
    performance: str


@dataclass
class Recommendation:
    finding_id: str
    current_approach: str
    alternatives: list[Alternative]
    recommended: str
    rationale: str
    assumptions: list[str]
    next_action: str
    keep_current: bool = False
    text_origin: str = "deterministic"   # or "llm" when reworded by an optional model


# ------------------------------------------------------------------------ patches

@dataclass(frozen=True)
class FileEdit:
    rel_path: str
    original_sha256: str
    new_content: str


@dataclass
class PatchProposal:
    patch_id: str
    finding_id: str
    strategy_index: int
    strategy_name: str
    root_cause: str
    intended_behaviour: str
    edits: list[FileEdit]
    unified_diff: str
    affected_files: list[str]
    regression_risks: list[str]
    suggested_tests: list[str]
    base_snapshot_hash: str
    patch_hash: str
    attempt: int = 1
    created_at: str = field(default_factory=utc_now)
    text_origin: str = "deterministic"
    # what the Code Improvement Agent read from earlier agents (advisor, baseline, critic, validation)
    context_used: list[str] = field(default_factory=list)


def compute_patch_hash(edits: list[FileEdit], base_snapshot_hash: str) -> str:
    payload = json.dumps(
        [[e.rel_path, e.original_sha256, e.new_content] for e in sorted(edits, key=lambda e: e.rel_path)]
        + [base_snapshot_hash],
        ensure_ascii=False,
    )
    return sha256_text(payload)


@dataclass
class CriticReview:
    patch_id: str
    in_scope: bool
    addresses_finding: bool
    issues: list[str]

    @property
    def ok(self) -> bool:
        return self.in_scope and self.addresses_finding and not self.issues


@dataclass(frozen=True)
class ApprovalRecord:
    patch_id: str
    patch_hash: str
    base_snapshot_hash: str
    decision: str            # "approved" | "rejected"
    decided_at: str
    note: str = ""


@dataclass
class CheckResult:
    name: str
    status: ValidationStatus
    detail: str
    duration_s: float = 0.0


@dataclass
class TestCaseResult:
    name: str
    outcome: str             # "passed" | "failed" | "error" | "skipped"
    message: str = ""


@dataclass
class ValidationResult:
    patch_id: str
    status: ValidationStatus
    checks: list[CheckResult]
    tests_passed: int = 0
    tests_failed: int = 0
    tests_errors: int = 0
    tests_skipped: int = 0
    test_cases: list[TestCaseResult] = field(default_factory=list)
    raw_output_tail: str = ""
    isolation_level: str = ""
    limitations: list[str] = field(default_factory=list)
    original_unchanged: bool | None = None
    working_copy: str = ""
    finished_at: str = field(default_factory=utc_now)


# ------------------------------------------------------------------- workflow log

@dataclass(frozen=True)
class PlanStep:
    key: str
    agent: str
    description: str
    enabled: bool = True
    reason: str = ""
    depends_on: tuple[str, ...] = ()    # steps that must be "done" before this one may run


@dataclass
class TaskPlan:
    goal: str
    steps: list[PlanStep]
    step_status: dict[str, str] = field(default_factory=dict)   # key -> pending/done/skipped/failed


@dataclass(frozen=True)
class AgentLogEntry:
    agent: str
    started_at: str
    finished_at: str
    state_before: str
    state_after: str
    summary: str
    outputs: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class DecisionRecord:
    from_state: str
    to_state: str
    event: str
    reason: str
    at: str = field(default_factory=utc_now)


@dataclass
class WorkflowContext:
    run_id: str
    state: WorkflowState = WorkflowState.RECEIVED
    goal: str = "Understand the repository, find risks, and propose validated fixes."
    plan: TaskPlan | None = None
    snapshot: RepoSnapshot | None = None
    summary: RepoSummary | None = None
    findings: list[Finding] = field(default_factory=list)
    recommendations: dict[str, Recommendation] = field(default_factory=dict)
    proposals: list[PatchProposal] = field(default_factory=list)
    reviews: dict[str, CriticReview] = field(default_factory=dict)
    approvals: list[ApprovalRecord] = field(default_factory=list)
    validations: list[ValidationResult] = field(default_factory=list)
    baseline: ValidationResult | None = None     # tests on the untouched original (trusted repos only)
    log: list[AgentLogEntry] = field(default_factory=list)
    decisions: list[DecisionRecord] = field(default_factory=list)
    selected_finding_id: str | None = None
    retries: int = 0
    blocked_reason: str = ""
    analysis_status: AnalysisStatus = AnalysisStatus.NOT_STARTED
    llm_label: str = "Mock LLM (deterministic text, no model used)"

    # convenience -----------------------------------------------------------
    def finding(self, finding_id: str) -> Finding | None:
        return next((f for f in self.findings if f.id == finding_id), None)

    @property
    def current_proposal(self) -> PatchProposal | None:
        return self.proposals[-1] if self.proposals else None

    @property
    def latest_validation(self) -> ValidationResult | None:
        return self.validations[-1] if self.validations else None


def to_jsonable(obj: Any) -> Any:
    """Convert dataclasses / enums / paths into plain JSON types."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj
