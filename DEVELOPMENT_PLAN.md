# CodeMind AI — Development Plan

Three controlled phases. Each phase ends with a verified report and **stops for explicit approval** ("APPROVE PHASE 2", "APPROVE PHASE 3").

## Phase 1 — Requirements, architecture, structure, technical design ✅ done

Outputs: `README.md`, `PROJECT_PLAN.md`, `ARCHITECTURE.md`, `SECURITY_PLAN.md`, `TEST_STRATEGY.md`, `DEVELOPMENT_PLAN.md`, `PROJECT_STATUS.md`, `CA3_REQUIREMENT_TRACEABILITY.md`, `requirements.txt`, `docs/architecture.{mmd,png,svg}`. No application code.

## Phase 2 — Working Streamlit PoC and core engine ✅ done (2.13 GitHub loader not built, by plan)

Built bottom-up; each step = write module → write its tests → run → fix → only then next step. Test results recorded in `PROJECT_STATUS.md` after each step.

| Step | Module(s) | Tests that must pass before moving on |
|---|---|---|
| 2.1 | `models.py`, `config.py`, `orchestrator/states.py` | T-STM-01 |
| 2.2 | `samples/student_grades_app` + `EXPECTED_FINDINGS.json` + `build_sample_zip.py`; confirm sample's own tests give the designed result (1 failing on purpose) | run sample tests directly, record output |
| 2.3 | `ingestion/zip_loader.py`, `file_filter.py`, `tree.py` | T-ZIP-*, T-FLT-* |
| 2.4 | `analysis/readme_parser.py`, `metadata.py`, `code_index.py`, Agent 1 | T-RDM-* |
| 2.5 | `analysis/ast_rules.py`, `evidence.py`, `prioritizer.py`, Agent 2 | T-RULE-*, T-BND-01 |
| 2.6 | `analysis/advisor_kb.py`, Agent 3 | advisor unit tests |
| 2.7 | `patching/fixers.py`, `diff.py`, Agent 4 | T-DIFF-01 |
| 2.8 | `patching/approval.py`, `apply.py` | T-APR-*, T-APP-* |
| 2.9 | `validation/syntax_check.py`, `sandbox_runner.py`, `report.py`, Agent 5 | T-VAL-* |
| 2.10 | `orchestrator/planner.py`, `orchestrator.py` (retry, BLOCKED) | T-STM-02, T-E2E-01 |
| 2.11 | `llm/adapter.py`, `mock_llm.py`, `ollama_llm.py` | T-LLM-01 |
| 2.12 | `app.py`, `ui/` (7 views), session-state & rerun safety | T-UI-01/02 |
| 2.13 | optional `github_loader.py` — only if 2.1–2.12 are green | T-GH-01 |
| 2.14 | full suite run, update README run instructions, `PROJECT_STATUS.md` | everything; failures documented, not hidden |

Exit criteria: as listed in the master prompt (core functions, UI, E2E on sample, approve/reject working, original preserved, real validation, recorded results, known defects, documented launch).

## Phase 3 — Verification, documentation, CA-3 evidence, presentation ✅ done (results: `TESTING_REPORT.md`)

1. Manual 12-step E2E in a real browser; capture **real** screenshots (headless Chromium is available in the build environment).
2. `TESTING_REPORT.md` (name, purpose, expected, actual, status, evidence, limits).
3. Finalise README, ARCHITECTURE, DEVELOPMENT_PLAN, PROJECT_STATUS; write `LIMITATIONS_AND_FUTURE_SCOPE.md`, `DEMO_CHECKLIST.md`.
4. 6–8 slide editable PPTX (python-pptx) using the architecture diagram and real screenshots, plus speaker notes.
5. 5-minute demo script (30s / 45s / 2m / 60s / 45s) and viva Q&A.
6. Final handover summary.

## Version control

The project currently lives in the shared project folder `codemind-ai/`. Pushing to GitHub happens **only when you ask**, to a repo you choose. Commit messages and contributor lists will not mention AI tools.
