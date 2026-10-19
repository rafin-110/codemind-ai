# CodeMind AI — Testing Report (CA-3 deliverable 6)

Every number below comes from a real run. Raw outputs are in `docs/test-evidence/`; screenshots are in `docs/screenshots/phase3/`. Nothing here is estimated or mocked unless it says so.

## 1. Environments and commands

| # | Environment | Command | Result | Evidence |
|---|---|---|---|---|
| E1 | Windows 11, Python 3.13.15, project venv (`requirements.txt` + pyflakes) | `python -m pytest -v -rs` | **105 passed** | `docs/test-evidence/phase3_pytest_windows_python3.13.txt` |
| E2 | Windows 11, Python 3.13.15, **fresh venv from `requirements.txt` only** (the examiner's setup) | `python -m pytest -v -rs` | **104 passed, 1 skipped** (optional pyflakes test, skipped by design) | `docs/test-evidence/phase3_pytest_windows_fresh_venv.txt` |
| E3 | Windows 11, real Chrome 155 driven by Playwright against `streamlit run app.py` | `python scripts/capture_demo.py` | **all steps passed** (15 screenshots, 2 downloaded reports) | `docs/test-evidence/phase3_browser_e2e_log.txt`, `docs/screenshots/phase3/` |
| E4 | Windows 11, Python 3.13.15 | `python scripts/evaluate_findings.py` | detection 9/9, fixes 8/9 validated | `docs/test-evidence/phase3_fix_evaluation.md` / `.json` |
| E5 | Linux, Python 3.13.16 (Phase 2 cloud build, before the Windows fix) | `python -m pytest -v -rs` | 104 passed | `docs/test-evidence/phase2_pytest_python3.13.txt` |
| E6 | Linux, Python 3.11.17, fresh venv (Phase 2) | `python -m pytest -v -rs` | 103 passed, 1 skipped | `docs/test-evidence/phase2_pytest_python3.11.txt` |

Versions used in E1–E4: streamlit 1.66.0, pytest 9.1.1, pyflakes 4.0.3 (E1 only), playwright 1.64.0 (E3 only).

## 2. Defect found and fixed in Phase 3

The first Windows run (E1, before the fix) gave **100 passed, 4 failed**: `test_retry_after_real_failure_then_pass`, `test_retries_exhausted_blocks`, `test_full_demo_flow`, `test_demo_through_ui`.

- **Cause.** The baseline step marks a finding *Confirmed* when its `file:line` appears in a failing test's traceback. Pytest prints OS-native paths, so on Windows the traceback says `grades\stats.py:7` while the finding says `grades/stats.py:7`. F-004 stayed *Potential*, the failing test was not linked to it, and the retry logic behaved differently.
- **Effect.** On the demo laptop (Windows) the headline "Confirmed by a real test" and the retry demo would have been wrong. The Linux runs (E5, E6) could not show this.
- **Fix.** `codemind/agents/critic_validator.py` normalises backslashes before matching (one line).
- **Regression test.** `test_baseline_links_windows_style_traceback_paths` rewrites the real test messages to Windows form and checks that F-004 is still Confirmed. It fails without the fix on every OS.
- **After the fix:** E1 105 passed, E2 104 passed + 1 skipped, E3 all steps passed.

## 3. Results by test ID

Mapping of IDs to test functions: `TEST_STRATEGY.md` §3. "Passed" = passed in E1 and E2.

| ID | Purpose | Expected | Actual | Status |
|---|---|---|---|---|
| T-ZIP-01 | valid sample ZIP extracts | all non-ignored files present, hashes recorded | 11 files extracted, hashes recorded, GitHub-style root folder stripped | Passed |
| T-ZIP-02 | path traversal | refused, nothing written | 5 variants (`../`, nested `..`, `/etc`, `C:/`, backslash) refused; nothing written | Passed (+ browser E3 step 15) |
| T-ZIP-03 | symlink entry | refused | refused | Passed |
| T-ZIP-04/05/06 | size, ratio, total, count, header mismatch | refused with specific reason | each refused with its own reason | Passed |
| T-FLT-01 | ignored dirs and binaries | skipped with reason | `.git`, `__pycache__`, `node_modules`, binary skipped | Passed |
| T-FLT-02 | sensitive files | inventoried, never read | `.env`, `id_rsa` listed as sensitive, not written | Passed |
| T-RDM-01/02 | README, metadata, structure | matches sample; missing README recorded | summary, entry point `main.py`, technologies, doc gaps correct | Passed |
| T-RULE-01..09 | each rule positive/negative | fires / stays quiet | 9 rules × positive + negative cases | Passed |
| T-RULE-10 | full sample vs ground truth | exact rule + file + line | **9/9 found, 0 extra** (also E4: precision 1.0, recall 1.0) | Passed |
| T-RULE-06 | secrets redacted | key never shown | not in evidence, diffs, test output or reports | Passed |
| T-BND-01 | empty / unparseable / nested / guarded code | no crash, correct result | correct | Passed |
| T-DIFF-01 | proposal diffs | expected `-`/`+` lines, only target file | 5 rules checked | Passed |
| T-APP-01 | reject | original unchanged, no copy | unchanged, no working copy (also E3 step 9) | Passed |
| T-APP-02/03 | approve | only the copy changes; original re-hash equal | equal; original files read-only | Passed |
| T-APP-04 | out-of-scope / traversal edits | critic rejects, apply refuses | both refused | Passed |
| T-VAL-01/02 | real failure → retry → pass | attempt 1 Failed, attempt 2 Passed | attempt 1 "Return a safe default" Failed on `test_average_empty_raises`; attempt 2 "Raise ValueError" Passed 9/9 (also E3 steps 10–12) | Passed |
| T-VAL-03 | patch with a syntax error | Failed at syntax, tests Not run | as expected | Passed |
| T-VAL-04 | test that hangs | Blocked (timeout) | Blocked, process killed | Passed |
| T-VAL-05 | untrusted upload | tests Not run → Partially verified | as expected; host secret variable not visible to tests (also E3 step 14) | Passed |
| T-APR-01..03 | wrong / old / tampered / stale approval | refused | all four refused | Passed |
| T-STM-01/02 | transition table, retry cap | illegal transitions raise; Blocked after cap | as expected | Passed |
| T-LLM-01 | Ollama down / bad output | deterministic fallback, labelled | fallback used and labelled (tested with a fake local server, **not a real model**) | Passed |
| T-GH-01 | GitHub URL input | — | feature not built | Not applicable |
| T-UI-01/02 | app renders; demo via UI | no exception, findings shown | `AppTest`: all 7 views render; demo works; `codemind/` never imports streamlit | Passed |
| T-E2E-01 | full orchestrator flow + edge cases | expected states, original unchanged | as expected; unsafe archive, docs-only repo, double analyse and unexpected exception all handled | Passed |

## 4. Browser end-to-end run (E3)

Real app, real Chrome, 1440×900. The script asserts on page text **and** on the downloaded JSON report. Log: `docs/test-evidence/phase3_browser_e2e_log.txt`.

| Step | Action | Checked | Screenshot |
|---|---|---|---|
| 1 | open app | title visible, state RECEIVED | `01_overview_empty.png` |
| 2 | load sample | repository explorer shown | `02_upload_sample_loaded.png` |
| 3 | run analysis | "Analysis finished: 9 findings" | `03_upload_analyzed.png` |
| 4 | overview, workflow | plan, transitions, agent log | `04_overview_after_analysis.png`, `05_agent_workflow.png` |
| 5 | findings → F-004 | Confirmed, linked to `test_average_empty_raises` | `06_findings_F004_confirmed.png` |
| 6 | advisor | alternatives per finding | `07_architecture_advisor.png` |
| 7 | F-001 → propose → **reject** | "original is unchanged and no working copy was made" | `08_proposal_F001.png`, `09_F001_rejected.png` |
| 8 | F-004 → propose → approve | attempt 1 FAILED, new strategy proposed | `10_proposal_F004_attempt1.png`, `11_F004_attempt2_after_failed_validation.png` |
| 9 | approve attempt 2 | "Validation result: Passed", original re-hashed unchanged | `12_validation_passed.png` |
| 10 | download JSON + Markdown | 9 findings, F-004 Confirmed, validations Failed→Passed, decisions rejected/approved/approved, original unchanged | `docs/test-evidence/phase3_ui_report.json`, `.md` |
| 11 | workflow after | full decision log | `13_agent_workflow_after.png` |
| 12 | upload ZIP **without** trust | 9 findings, no baseline test run | `14_upload_untrusted_zip.png` |
| 13 | upload `../../evil.py` ZIP | "Archive rejected: entry '../../evil.py' escapes the workspace (path traversal)" | `15_upload_traversal_refused.png` |

## 5. Agent quality on the synthetic sample (E4)

Full table: `docs/test-evidence/phase3_fix_evaluation.md`. For each finding the script runs a fresh orchestrator and approves every proposal itself.

| Measure | Result |
|---|---|
| Detection vs `samples/EXPECTED_FINDINGS.json` (ground truth located by text search, not by the rule engine) | 9/9 at exact rule + file + line, 0 extra (precision 1.0, recall 1.0) |
| Findings that reached VALIDATED | 8/9 (7 on the first strategy, F-004 after one retry) |
| Finding with no automatic fix | F-006 (R008, unvalidated input): advisor explains options, no patch by design |
| Original unchanged after every validation | yes (9/9 runs) |
| Analysis time incl. baseline test run | about 1.2 s on the sample |

In 7 of the Passed validations, one test still fails: `test_average_empty_raises`. It already fails on the untouched original and belongs to F-004. The pass rule lists it as pre-existing instead of blaming an unrelated patch, and it passes once F-004 is fixed.

**What these numbers do not show.** The sample was written by us with planted issues, so 9/9 shows the rules work as designed, not how they do on real-world code. See `LIMITATIONS_AND_FUTURE_SCOPE.md`.

## 6. Not verified

- Ollama with a real local model (only a fake local server was tested).
- macOS.
- Real-world repositories beyond the synthetic sample and the generated test archives.
- Resource limits (POSIX only) and `unshare` network isolation on this Windows machine. The UI reports both as unavailable here, which is correct.
