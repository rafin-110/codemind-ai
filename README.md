# CodeMind AI

**An Agentic AI Code Review Assistant for Understanding, Debugging, and Improving AI-Generated Code**

Domain: Code Review (Software Development and Developer Productivity) · University CA-3 Proof of Concept

> **Status: complete (all three phases).** 105 tests pass on Windows, plus a browser end-to-end run in real Chrome. Results: `TESTING_REPORT.md`. Presentation: `presentation/`.

## What it does

CodeMind AI helps developers who rely on AI coding tools understand and safely improve their codebase:

**ANALYZE → EXPLAIN WITH EVIDENCE → COMPARE SOLUTIONS → REQUEST HUMAN APPROVAL → APPLY APPROVED PATCH TO A COPY → VALIDATE → REPORT**

- Upload a repository as a ZIP, or load the bundled synthetic sample.
- A Planner/Orchestrator (explicit state machine) runs five agents over one shared, typed workflow context:
  1. **Repository Understanding**: README, structure, entry points, dependencies, import graph, documentation gaps, with file/line evidence.
  2. **Bug & Risk Analysis**: deterministic Python AST rules R000–R009 (syntax errors, division by zero, swallowed exceptions, `eval`, mutable defaults, `shell=True`, hard-coded secrets, SQL injection, unvalidated input, `== None`), plus pyflakes undefined names if pyflakes is installed.
  3. **Solution & Architecture Advisor**: compares the current approach with alternatives and trade-offs, and says when the current approach is fine.
  4. **Code Improvement**: minimal patch proposal with a unified diff, risks and suggested tests.
  5. **Critic & Validation**: runs the repo's tests on the untouched original (to confirm findings), reviews each proposal before you see it, then validates approved patches on an isolated copy (syntax check, rule re-check, real `pytest` run). A failed validation sends feedback to Agent 4 for a different strategy, up to 2 retries, then BLOCKED.
- Nothing is applied without your explicit approval, bound to the exact patch hash. The original upload is never modified. Nothing is committed or pushed.

## Real vs. mocked vs. optional

| Part | Nature |
|---|---|
| ZIP ingestion, AST analysis, prioritisation, diffs, approval, patching, test execution, reports | **Real**, deterministic Python, covered by tests |
| Explanations and alternative comparisons | **Deterministic** knowledge-base text filled with project facts. The default "LLM" is a `MockLLM` that returns this text unchanged and is labelled in the UI. |
| Local Ollama LLM | **Optional** (`CODEMIND_LLM=ollama`). Only rewords explanations; output is validated and labelled. Tested against a fake local server, not a real model. |
| Public GitHub URL input | **Not implemented** (future scope). ZIP upload covers the requirement. |
| Sample repository | **Synthetic**, written for the demo, with planted issues documented in `samples/EXPECTED_FINDINGS.json` |

## Setup and run

Requires Python 3.11 or newer. No API keys, no paid services, no internet needed at runtime.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py                 # opens http://localhost:8501
python -m pytest -q                  # run the test suite (104 passed, 1 skipped without pyflakes)
```

Evidence scripts (optional, `pip install -r requirements-dev.txt`):

```bash
python scripts/capture_demo.py       # browser end-to-end run + screenshots
python scripts/evaluate_findings.py  # fix every finding, record outcomes
python presentation/build_deck.py    # rebuild the PPT
```

Optional extras: `pip install pyflakes` adds rule PF01; `set CODEMIND_LLM=ollama` (Windows) or `export CODEMIND_LLM=ollama` uses a local Ollama model (`llama3.2` at `http://localhost:11434`).

## Two-minute demo path

1. **Upload & Explorer** → *Load sample repository* → *Run analysis (all agents)*. 9 findings; F-004 (division by zero) is marked *Confirmed* because the sample's own test fails on it.
2. **Findings** → pick F-001 → *Ask the Code Improvement Agent for a fix* → **Proposed Changes** → *Reject*. The original stays unchanged and no copy is made.
3. **Findings** → pick F-004 → ask for a fix → *Approve and validate*. Strategy 1 (return 0.0) fails the repo test `test_average_empty_raises`, so the agent proposes strategy 2 (raise ValueError).
4. Approve again → **Validation Results**: 9 passed, 0 failed, original re-hashed unchanged. Download the JSON or Markdown report.
5. **Agent Workflow** shows the plan, every state transition with its reason, and the agent log.

Screenshots from a real run are in `docs/screenshots/phase3/`. Full demo script: `presentation/DEMO_SCRIPT.md`.

## Project layout

```
app.py                 Streamlit entry (navigation only)
codemind/              all logic; never imports streamlit
  ingestion/           safe ZIP extraction, filtering, tree
  analysis/            README/metadata/code index, AST rules, evidence, advisor knowledge base
  agents/              the five agents
  orchestrator/        state machine, planner, orchestrator
  patching/            fixers, diff, approval binding, copy-only apply
  validation/          syntax check, sandboxed pytest runner, reports
  llm/                 adapter, mock, optional Ollama
ui/                    Streamlit views (7 pages)
samples/               synthetic sample repo + ground truth
tests/                 unit and integration tests
scripts/               browser E2E and evaluation scripts
presentation/          PPT, demo script, viva Q&A
docs/                  architecture diagram, screenshots
```

Runtime files go to `workspace/` (one folder per run, replaced on the next load) and are git-ignored.

## Documents

| File | Purpose |
|---|---|
| `PROJECT_PLAN.md` | problem statement, domain justification, challenge vs. solution, scope |
| `ARCHITECTURE.md` | diagram, agents, state machine, data structures, UI, stack, directory tree, why no database |
| `SECURITY_PLAN.md` | security controls and failure handling |
| `TEST_STRATEGY.md` | test levels and the full test-case list mapped to test files |
| `DEVELOPMENT_PLAN.md` | phase-by-phase build order |
| `PROJECT_STATUS.md` | what exists, verified results, open issues |
| `CA3_REQUIREMENT_TRACEABILITY.md` | every CA-3 deliverable → file → feature → verification |
| `TESTING_REPORT.md` | actual results of every test level, defects found, what is not verified |
| `LIMITATIONS_AND_FUTURE_SCOPE.md` | honest limits and next steps |
| `DEMO_CHECKLIST.md` | pre-demo checks and fallback plan |
| `presentation/` | PPT (+ `build_deck.py`), 5-minute demo script, viva Q&A |
| `docs/architecture.mmd` / `.png` / `.svg` | architecture diagram |
