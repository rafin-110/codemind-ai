# CodeMind AI — Test Strategy

Principles: test real behaviour, not mocks of the code under test; every result reported in `PROJECT_STATUS.md` / `TESTING_REPORT.md` comes from an actual run with its command and output. A syntax check is not a test; passing tests do not prove absence of bugs.

## 1. Levels

| Level | Tool | What | Where |
|---|---|---|---|
| Unit | pytest | each core function in isolation, using in-memory or `tmp_path` fixtures | `tests/unit/` |
| Integration | pytest | full orchestrator run on the synthetic sample, no UI | `tests/integration/test_workflow_end_to_end.py` |
| UI smoke | `streamlit.testing.v1.AppTest` | app imports, renders every view, sample load + analyse via button | `tests/integration/test_streamlit_app.py` |
| Browser E2E (Phase 3) | Playwright + real Chrome against `streamlit run app.py` | full demo path, ZIP upload, malicious ZIP; asserts on page text and on the downloaded JSON report; saves screenshots | `scripts/capture_demo.py` → `docs/screenshots/phase3/`, `docs/test-evidence/phase3_browser_e2e_log.txt` |

Malicious archives (zip-slip, symlink, bomb, too many files) are **generated inside the tests** with `zipfile`, so no dangerous binaries are committed.

## 2. Required test cases (maps to the 14 minimums in the brief)

| ID | Brief # | Test | Expected |
|---|---|---|---|
| T-ZIP-01 | 1 | extract valid sample ZIP | all non-ignored files present, hashes recorded |
| T-ZIP-02 | 2 | entries `../x.py`, `/etc/x`, `C:\x`, `a/../../x` | `UnsafeArchiveError`, nothing written outside target |
| T-ZIP-03 | 2 | symlink entry | rejected |
| T-ZIP-04/05/06 | 1 | oversized, high-ratio, too many files | rejected with specific reason |
| T-FLT-01 | 3 | `.git/`, `__pycache__/`, `node_modules/`, binary file | skipped with reason |
| T-FLT-02 | 3 | `.env`, `id_rsa` | inventoried as sensitive, content never read |
| T-RDM-01 | 4 | README title/sections parsed; requirements & entry point detected | matches sample |
| T-RDM-02 | 4 | repo without README | doc gap recorded, no crash |
| T-RULE-01..09 | 5 | each rule on positive and negative snippets | fires / does not fire |
| T-RULE-10 | 5, 6 | full sample vs `EXPECTED_FINDINGS.json` | every planted issue found at the exact file + line |
| T-RULE-06 | 5 | secret evidence | value redacted |
| T-BND-01 | 7 | normal / boundary / invalid inputs to rules and fixers (empty file, unparseable file, nested functions, guarded division) | correct no-finding / R000 / finding |
| T-DIFF-01 | 8 | proposal for R001, R004 | unified diff has expected `-`/`+` lines; only target file |
| T-APP-01 | 9 | propose then **reject** | original snapshot hash unchanged, no working copy created |
| T-APP-02 | 10 | **approve** | working copy changed, original hash unchanged, file mode still read-only |
| T-APP-03 | 9, 10 | report "original unchanged" check | re-hash equals ingest hash |
| T-APP-04 | — | patch touching another file / `../` path | critic rejects, apply refuses |
| T-VAL-01 | 11 | approved R001 strategy 2 on sample | pytest run, counts parsed from JUnit XML, status PASSED |
| T-VAL-02 | 12 | R001 strategy 1 | status FAILED, failing test name reported, retry triggered |
| T-VAL-03 | 12 | patch that breaks syntax (injected in test) | FAILED at syntax stage, tests NOT_RUN |
| T-VAL-04 | — | test exceeding timeout | BLOCKED (timeout) |
| T-VAL-05 | — | uploaded repo without trust opt-in | tests NOT_RUN, overall PARTIALLY_VERIFIED |
| T-APR-01 | 13 | approval for patch A used on patch B | refused |
| T-APR-02 | 13 | proposal regenerated after approval | old approval invalid |
| T-APR-03 | 13 | original file hash changed after proposal | approval refused |
| T-STM-01 | — | every legal transition; illegal ones raise | transition table enforced |
| T-STM-02 | — | retries capped at 2 then BLOCKED | BLOCKED with all attempts logged |
| T-LLM-01 | — | Ollama unreachable / returns junk | deterministic fallback, labelled |
| T-GH-01 | — | (only if the optional GitHub loader is built) invalid URLs, non-github hosts, network failure | rejected / clear error; ZIP path still works offline |
| T-UI-01 | 14 | `AppTest.from_file("app.py").run()` | no exception; all 7 views render |
| T-UI-02 | 14 | load sample + analyse via UI buttons | findings table non-empty; Approve disabled until a proposal exists |
| T-E2E-01 | — | orchestrator: load → analyse → propose R002 → reject → propose R001 → approve → fail → retry → approve → pass → report | matches expected states; original unchanged |

## 3. Test ID → test function (as implemented)

| ID | Test function(s) |
|---|---|
| T-ZIP-01 | `tests/unit/test_zip_loader.py::test_valid_sample_zip_extracts_all_files`, `test_github_style_common_root_is_stripped`, `test_not_a_zip` |
| T-ZIP-02 | `test_zip_loader.py::test_path_traversal_rejected_and_nothing_written` (5 parametrised paths) |
| T-ZIP-03 | `test_zip_loader.py::test_symlink_rejected` |
| T-ZIP-04/05/06 | `test_zip_loader.py::test_oversized_archive_rejected`, `test_zip_bomb_ratio_rejected`, `test_total_uncompressed_cap`, `test_too_many_files`, `test_header_size_mismatch_detected` |
| T-FLT-01 | `test_zip_loader.py::test_ignored_dirs_and_binary_skipped` |
| T-FLT-02 | `test_zip_loader.py::test_sensitive_files_inventoried_but_not_written` |
| T-RDM-01 | `tests/unit/test_repo_understanding.py::test_sample_summary`, `test_readme_parser_sections_and_code_blocks` |
| T-RDM-02 | `test_repo_understanding.py::test_repo_without_readme_records_gap`, `test_unparseable_file_is_reported_not_crashing` |
| T-RULE-01..09 | `tests/unit/test_ast_rules.py::test_rule_fires_on_positive_case`, `test_rule_quiet_on_negative_case`, `test_eval_on_input_is_critical_but_dynamic_string_is_high`, `test_os_system_flagged`, `test_fstring_and_format_sql_flagged`, `test_test_files_are_not_flagged`, `test_pyflakes_optional_undefined_name` |
| T-RULE-10 | `test_ast_rules.py::test_sample_matches_ground_truth_exactly`, `test_findings_have_all_required_fields_and_ids` |
| T-RULE-06 (redaction) | `test_ast_rules.py::test_secret_never_in_evidence`, `test_repo_understanding.py::test_redaction` |
| T-BND-01 | `test_ast_rules.py::test_boundary_inputs`, `test_syntax_error_finding_has_line` |
| T-DIFF-01 | `tests/unit/test_patching_and_validation.py::test_proposal_diff_contents` (5 rules), `test_no_automatic_fix_returns_to_findings`, `test_fixers_refuse_unsafe_patterns` |
| T-APP-01 | `test_patching_and_validation.py::test_reject_leaves_original_and_creates_no_copy` |
| T-APP-02/03 | `test_patching_and_validation.py::test_approve_changes_only_the_copy`, `test_zip_loader.py::test_original_is_read_only` |
| T-APP-04 | `test_patching_and_validation.py::test_out_of_scope_edit_rejected_by_critic_and_apply`, `test_traversal_edit_rejected`, `test_apply_refuses_without_valid_approval` |
| T-VAL-01/02 | `test_patching_and_validation.py::test_retry_after_real_failure_then_pass`, `test_runner_counts_real_results`, `test_baseline_links_windows_style_traceback_paths` |
| T-VAL-03 | `test_patching_and_validation.py::test_syntax_failure_reported_and_tests_not_run` |
| T-VAL-04 | `test_patching_and_validation.py::test_timeout_is_blocked` |
| T-VAL-05 | `test_patching_and_validation.py::test_untrusted_upload_is_partially_verified`, `test_runner_env_is_stripped` |
| T-APR-01..03 | `test_patching_and_validation.py::test_approval_with_wrong_hash_is_refused`, `test_old_approval_cannot_authorise_a_newer_proposal`, `test_tampered_proposal_is_refused`, `test_changed_original_invalidates_approval` |
| T-STM-01 | `tests/unit/test_states.py` (all 6 tests, 10 cases) |
| T-STM-02 | `test_patching_and_validation.py::test_retries_exhausted_blocks`, `test_states.py::test_failed_validation_can_retry_or_block` |
| T-LLM-01 | `tests/unit/test_llm_and_advisor.py::test_ollama_unreachable_falls_back`, `test_ollama_output_is_validated`; advisor: `test_every_rule_has_advice_with_alternatives`, `test_advisor_on_sample` |
| T-GH-01 | not applicable: the GitHub loader was not built (future scope) |
| T-UI-01 | `tests/integration/test_streamlit_app.py::test_every_view_renders_before_and_after_analysis`, `test_core_package_does_not_import_streamlit` |
| T-UI-02 | `test_streamlit_app.py::test_demo_through_ui` + browser E2E `scripts/capture_demo.py` |
| T-E2E-01 | `tests/integration/test_workflow_end_to_end.py::test_full_demo_flow` + edge cases `test_rejected_archive_blocks_with_reason`, `test_docs_only_repo_is_structure_only`, `test_analyze_twice_is_refused`, `test_unexpected_error_fails_safe` |

Actual results for every row are in `TESTING_REPORT.md`.

## 4. How to run

```bash
python -m pip install -r requirements.txt
python -m pytest -q                       # all tests
python -m pytest tests/unit -q            # unit only
python -m pytest --junitxml=reports/junit.xml   # machine-readable evidence

# browser E2E + screenshots (dev extra: pip install -r requirements-dev.txt)
python scripts/capture_demo.py
```

## 5. Evidence rules

- Record command, date, Python version, OS, and the pass/fail/skip counts exactly as printed.
- Failing or skipped tests are reported, not removed. Tests are never weakened to get green.
- Anything not executed is listed as **Not verified**.
