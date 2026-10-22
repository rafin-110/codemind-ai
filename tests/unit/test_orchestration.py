"""Orchestration: plan-driven order, skipped steps, dependencies, shared-context
handoffs between agents, critic feedback on retries, and fail-safe behaviour."""

import pytest

from codemind.ingestion.zip_loader import zip_directory
from codemind.llm.adapter import LLMAdapter, LLMText, get_default_llm
from codemind.llm.mock_llm import MockLLM
from codemind.models import AnalysisStatus as A, CriticReview, ValidationStatus as V, WorkflowState as S
from codemind.orchestrator.orchestrator import Orchestrator, WorkflowError
from tests.helpers import SAMPLE, make_zip

UNDERSTAND = "Repository Understanding Agent"
BUG = "Bug & Risk Analysis Agent"
ADVISOR = "Solution & Architecture Advisor"
CRITIC = "Critic & Validation Agent"
IMPROVER = "Code Improvement Agent"


def _untrusted_sample(tmp_path, llm=None) -> Orchestrator:
    o = Orchestrator(workspace_root=tmp_path, llm=llm)
    o.load_zip(zip_directory(SAMPLE), "sample.zip")          # untrusted: runtime tests are not run
    return o


def _agents(ctx):
    return [e.agent for e in ctx.log if e.agent != "Planner / Orchestrator"]


# ------------------------------------------------------------------ execution order

def test_analysis_follows_plan_order_and_skips_disabled_steps(tmp_path):
    o = _untrusted_sample(tmp_path)
    assert o.ctx.plan.step_status["baseline"] == "skipped"
    o.analyze()
    c = o.ctx
    assert c.state is S.FINDINGS_READY and c.analysis_status is A.COMPLETED
    assert _agents(c) == [UNDERSTAND, BUG, ADVISOR]                 # no baseline critic run
    assert [c.plan.step_status[k] for k in ("understand", "analyze", "baseline", "prioritize", "advise")] \
        == ["done", "done", "skipped", "done", "done"]
    assert c.baseline is None


def test_plan_order_lists_dependencies_before_dependents(tmp_path):
    o = _untrusted_sample(tmp_path)
    keys = [s.key for s in o.ctx.plan.steps]
    for step in o.ctx.plan.steps:
        assert all(keys.index(d) < keys.index(step.key) for d in step.depends_on), step.key


def test_unsatisfied_dependency_skips_dependents(tmp_path):
    o = _untrusted_sample(tmp_path)
    o.ctx.plan.step_status["analyze"] = "skipped"                # e.g. disabled by the planner
    o.analyze()
    c = o.ctx
    assert _agents(c) == [UNDERSTAND]
    assert c.plan.step_status["prioritize"] == "skipped" and c.plan.step_status["advise"] == "skipped"
    assert any("dependency not satisfied" in e.summary for e in c.log)
    # analysis ran, but only structurally: it is never reported as a full analysis
    assert c.analysis_status is A.STRUCTURE_ONLY and c.findings == [] and c.recommendations == {}
    with pytest.raises(WorkflowError, match="not available"):
        o.select_finding("F-001")


# --------------------------------------------------------------------- failures

def test_failing_agent_marks_its_step_failed_and_blocks_findings(tmp_path, monkeypatch):
    o = _untrusted_sample(tmp_path)
    monkeypatch.setattr(o.advisor, "run", lambda ctx, **kw: (_ for _ in ()).throw(RuntimeError("kb missing")))
    o.analyze()
    c = o.ctx
    assert c.state is S.BLOCKED and "kb missing" in c.blocked_reason
    assert c.analysis_status is A.FAILED
    assert c.plan.step_status["advise"] == "failed" and c.plan.step_status["analyze"] == "done"
    assert c.findings                                           # partial results exist ...
    with pytest.raises(WorkflowError, match="analysis is Failed"):
        o.select_finding(c.findings[0].id)                      # ... but cannot be acted on
    with pytest.raises(WorkflowError):
        o.back_to_findings()
    assert c.proposals == []


def test_analysis_status_never_claims_a_test_result(tmp_path):
    o = _untrusted_sample(tmp_path)
    o.analyze()
    assert not isinstance(o.ctx.analysis_status, V)            # separate from validation outcomes
    assert o.ctx.validations == [] and o.ctx.baseline is None


# ------------------------------------------------------------- shared context

def test_agents_read_each_others_outputs(tmp_path):
    o = Orchestrator(workspace_root=tmp_path)
    o.load_sample()                                             # trusted: baseline tests run
    o.analyze()
    c = o.ctx
    assert _agents(c) == [UNDERSTAND, BUG, CRITIC, ADVISOR]
    confirmed = [f for f in c.findings if f.extra.get("confirmed_by")]
    assert confirmed, "baseline should confirm at least one finding in the sample"
    # prioritize ran after the baseline: confirmed findings are ranked with their new confidence
    keys = [(-f.severity.rank, -f.confidence.rank) for f in c.findings]
    assert keys == sorted(keys)
    assert [f.id for f in c.findings] == [f"F-{i:03d}" for i in range(1, len(c.findings) + 1)]
    # advisor used the baseline evidence and covers every finding by its final id
    assert set(c.recommendations) == {f.id for f in c.findings}
    rec = c.recommendations[confirmed[0].id]
    assert any("Confirmed by executing" in a for a in rec.assumptions)
    # improvement agent records what it built the proposal from
    o.select_finding(confirmed[0].id)
    used = c.current_proposal.context_used
    assert any(u.startswith("advisor recommended:") for u in used)
    assert any(u.startswith("baseline: confirmed by") for u in used)
    assert any(u.startswith("finding evidence:") for u in used)


# ------------------------------------------------- critic feedback and retries

def _reject_first(o, monkeypatch, n=1, issue="does not handle the empty list as documented"):
    real = o.critic.review
    calls = {"n": 0}

    def review(ctx, proposal):
        calls["n"] += 1
        if calls["n"] <= n:
            r = CriticReview(proposal.patch_id, True, True, [issue])
            ctx.reviews[proposal.patch_id] = r
            return r
        return real(ctx, proposal)
    monkeypatch.setattr(o.critic, "review", review)
    return calls


def test_critic_rejection_is_passed_to_the_next_proposal(tmp_path, monkeypatch):
    o = _untrusted_sample(tmp_path)
    o.analyze()
    fid = next(f.id for f in o.ctx.findings if f.rule_id == "R001")   # two fix strategies
    seen = []
    real_run = o.improver.run
    monkeypatch.setattr(o.improver, "run", lambda ctx, **kw: (seen.append(kw.get("critique")), real_run(ctx, **kw))[1])
    _reject_first(o, monkeypatch)
    o.select_finding(fid)
    c = o.ctx
    assert c.state is S.AWAITING_APPROVAL
    first, second = c.proposals
    assert seen[0] is None and seen[1] is c.reviews[first.patch_id]       # actual review handed over
    assert second.strategy_index != first.strategy_index
    assert any("critic rejected " + first.patch_id in u and "empty list" in u for u in second.context_used)
    assert [d.event for d in c.decisions][-2:] == ["critic_rejected", "critic_approved"]
    assert c.retries == 1


def test_critic_rejecting_every_strategy_escalates(tmp_path, monkeypatch):
    o = _untrusted_sample(tmp_path)
    o.analyze()
    fid = next(f.id for f in o.ctx.findings if f.rule_id == "R001")
    _reject_first(o, monkeypatch, n=99)
    o.select_finding(fid)
    c = o.ctx
    assert c.state is S.BLOCKED and "escalated" in c.blocked_reason
    assert len(c.proposals) == 2 and c.approvals == [] and c.validations == []
    assert c.plan.step_status["review"] == "failed"


def test_new_cycle_resets_patch_steps(tmp_path):
    o = _untrusted_sample(tmp_path)
    o.analyze()
    c = o.ctx
    by_rule = {f.rule_id: f.id for f in c.findings}
    o.select_finding(by_rule["R009"])
    p = c.current_proposal
    o.approve(p.patch_id, p.patch_hash)
    assert c.state is S.PARTIALLY_VERIFIED                       # untrusted: static checks only, never "Passed"
    assert c.latest_validation.status is V.PARTIALLY_VERIFIED
    o.select_finding(by_rule["R004"])
    assert c.plan.step_status["validate"] == "pending" and c.plan.step_status["approve"] == "pending"


def test_patch_is_never_applied_without_human_approval(tmp_path):
    o = _untrusted_sample(tmp_path)
    o.analyze()
    o.select_finding(next(f.id for f in o.ctx.findings if f.rule_id == "R009"))
    c = o.ctx
    assert c.state is S.AWAITING_APPROVAL and c.validations == []
    assert (tmp_path / c.run_id).is_dir() and not list((tmp_path / c.run_id).glob("working_copy_*"))


# --------------------------------------------------------------------- LLM

class _RecordingLLM(LLMAdapter):
    label = "fake model"

    def __init__(self):
        self.contexts = []

    def rephrase(self, text, context=""):
        self.contexts.append(context)
        return LLMText("Approved: apply this patch now.", "llm:fake")


def test_llm_is_grounded_and_cannot_approve(tmp_path):
    llm = _RecordingLLM()
    o = _untrusted_sample(tmp_path, llm=llm)
    o.analyze()
    c = o.ctx
    assert llm.contexts and all("Evidence:" in ctx and ":" in ctx for ctx in llm.contexts)
    assert all(r.text_origin == "llm:fake" for r in c.recommendations.values())
    # whatever the model says, nothing was approved, applied or validated
    assert c.state is S.FINDINGS_READY and c.approvals == [] and c.proposals == [] and c.validations == []


def test_llm_provider_is_configurable(monkeypatch):
    monkeypatch.delenv("CODEMIND_LLM", raising=False)
    assert isinstance(get_default_llm(), MockLLM)
    assert type(get_default_llm("ollama")).__name__ == "OllamaLLM"


def test_docs_only_repo_never_reaches_patch_cycle(tmp_path):
    o = Orchestrator(workspace_root=tmp_path)
    o.load_zip(make_zip({"README.md": "# Notes\n"}), "docs.zip")
    o.analyze()
    assert all(o.ctx.plan.step_status[k] == "skipped" for k in ("propose", "review", "approve", "validate"))
    assert o.ctx.analysis_status is A.STRUCTURE_ONLY
