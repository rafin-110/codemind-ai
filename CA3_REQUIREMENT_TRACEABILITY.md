# CA-3 Requirement Traceability Matrix

Status key: **Designed** (Phase 1 doc exists) · **Implemented** · **Verified** (evidence recorded) · **Not started**.
Status column is updated at the end of every phase. Final status (Phase 3, 2026-10-20): Verified = implemented and checked by the tests/evidence named in the row; results in `TESTING_REPORT.md`.

## A. The seven mandatory CA-3 deliverables

| # | CA-3 deliverable | Concrete file(s) | Feature / content | Verification method | Phase | Status |
|---|---|---|---|---|---|---|
| 1 | Problem statement + domain justification | `PROJECT_PLAN.md` §1; PPT slide 1 | problem, users, domain rationale | examiner reading; slide review | 1, 3 | Verified |
| 2 | Existing challenges + proposed solution | `PROJECT_PLAN.md` §2; PPT slides 2–3 | challenge → response table | review; each "response" row traced to a feature in table B | 1, 3 | Verified |
| 3 | Agent roles, responsibilities, orchestration workflow | `ARCHITECTURE.md` §2–4; `codemind/agents/*`, `codemind/orchestrator/*`; UI view 3 | 5 agents + planner, state machine, retry, approval gate | T-STM-01/02, T-E2E-01; agent log visible in UI | 1, 2 | Verified |
| 4 | Complete architecture diagram | `docs/architecture.mmd` (+ `.png`, `.svg`), embedded in `ARCHITECTURE.md` §1; PPT slide 4 | developer, UI, ingestion, planner, 5 agents, tools, shared state, approval/rejection, original vs copy, retry/failure, report | rendered with mermaid-cli (done in Phase 1); checklist §C below | 1, 3 | Verified |
| 5 | Working Streamlit PoC on synthetic data | `app.py`, `ui/views/*`, `samples/student_grades_app` | 7 views, full workflow on sample repo | T-UI-01/02, T-E2E-01, manual demo with screenshots | 2, 3 | Verified |
| 6 | Output validation, actual results, limitations, future scope | `codemind/validation/*`, UI view 7, `TESTING_REPORT.md`, `LIMITATIONS_AND_FUTURE_SCOPE.md` | real syntax + pytest results, report download, honest limits | T-VAL-01..05; recorded pytest output | 2, 3 | Verified |
| 7 | Professional PPT | `presentation/CodeMind_AI_CA3.pptx`, `presentation/DEMO_SCRIPT.md`, `presentation/VIVA_QA.md` | 6–8 slides, 5-min script, viva answers | open PPTX, render to images and check; timed rehearsal | 3 | Verified |

## B. Functional requirements from the master prompt

| Requirement | File / module | Test | Phase | Status |
|---|---|---|---|---|
| ZIP upload, safe extraction, traversal/bomb/size limits | `ingestion/zip_loader.py`, `config.py` | T-ZIP-01..06 | 2 | Verified |
| Ignore irrelevant & sensitive files | `ingestion/file_filter.py` | T-FLT-01/02 | 2 | Verified |
| Optional public GitHub input | `ingestion/github_loader.py` | T-GH-01 | 2 (stretch) | Not built (future scope) |
| README / metadata / tree / tech detection | `analysis/readme_parser.py`, `metadata.py`, `ingestion/tree.py` | T-RDM-01/02 | 2 | Verified |
| Agent 1 Repository Understanding | `agents/repo_understanding.py` | T-RDM-01, T-E2E-01 | 2 | Verified |
| Agent 2 Bug & Risk (evidence, severity, confidence) | `agents/bug_risk.py`, `analysis/ast_rules.py`, `evidence.py` | T-RULE-01..10, T-BND-01 | 2 | Verified |
| Agent 3 Solution & Architecture Advisor | `agents/solution_advisor.py`, `analysis/advisor_kb.py` | unit test per rule: ≥1 alternative or explicit keep-current | 2 | Verified |
| Agent 4 Code Improvement (proposal, diff, tests suggested) | `agents/code_improvement.py`, `patching/fixers.py`, `diff.py` | T-DIFF-01 | 2 | Verified |
| Agent 5 Critic & Validation | `agents/critic_validator.py`, `validation/*` | T-APP-04, T-VAL-01..05 | 2 | Verified |
| Planner/Orchestrator state machine, decision log | `orchestrator/*` | T-STM-01/02 | 2 | Verified |
| Human approval / rejection, stale-approval invalidation | `patching/approval.py`, UI view 6 | T-APR-01..03, T-APP-01/02 | 2 | Verified |
| Original preserved; patch only on copy | `patching/apply.py` | T-APP-01..03 | 2 | Verified |
| Bounded retry, BLOCKED escalation | `orchestrator/orchestrator.py` | T-STM-02, T-VAL-02 | 2 | Verified |
| Validation statuses Passed/Failed/Not run/Blocked/Partially verified | `models.py`, `validation/report.py` | T-VAL-01..05 | 2 | Verified |
| Works without paid API; optional Ollama, labelled | `llm/*` | T-LLM-01; run with no network | 2 | Verified |
| UI separate from logic | `ui/` vs `codemind/` | review: no `import streamlit` under `codemind/` (checked by a test) | 2 | Verified |
| Downloadable report | `validation/report.py`, view 7 | T-E2E-01 asserts report content | 2 | Verified |
| Security controls defined before implementation | `SECURITY_PLAN.md` | review (Phase 1) | 1 | Verified |
| Docs: README, PLAN, ARCH, DEV PLAN, STATUS, requirements, test strategy, diagram, traceability | repo root | Phase 1 file check (see PROJECT_STATUS) | 1 | Verified |
| Phase 3 docs: TESTING_REPORT, LIMITATIONS_AND_FUTURE_SCOPE, demo script, checklist, viva | repo root, `presentation/` | review against implementation | 3 | Verified |

## C. Architecture diagram completeness check (deliverable 4)

| Required element | Node(s) in `docs/architecture.mmd` |
|---|---|
| Developer | `DEV` |
| Streamlit UI | `UI` |
| Repository ingestion | `INGEST` subgraph (`ZIP`, `GH`, `SAFE`) |
| Planner / Orchestrator | `CORE` subgraph, `PLAN` |
| Repository Understanding Agent | `A1` |
| Bug & Risk Analysis Agent | `A2` |
| Solution & Architecture Advisor | `A3` |
| Code Improvement Agent | `A4` |
| Critic & Validation Agent | `A5R` (review), `VAL` (validation) |
| Static analysis and test tools | `TOOLS` subgraph (`T1`–`T5`) |
| Shared structured findings & workflow state | `STATE` |
| Human approval and rejection | `APPR`, `REJ` |
| Original repo vs isolated working copy | `ORIG`, `COPY` |
| Conditional retry and failure handling | `D1`, `D2`, `D3`, `A5R → A4`, `BLK`, `ERR`, `PART` |
| Final validation report | `REP` |
