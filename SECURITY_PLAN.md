# CodeMind AI — Security Controls and Failure Handling

Defined in Phase 1, **before** implementation. Each control has a test ID from `TEST_STRATEGY.md`.

## 1. Threat model (PoC scope)

| Asset | Threat | Source |
|---|---|---|
| Host machine / user files | malicious archive writes outside workspace (zip-slip, symlinks), zip bombs | uploaded ZIP / GitHub zipball |
| Host machine | uploaded code executed during "analysis" or "testing" | uploaded repo |
| Secrets | API keys / `.env` contents shown in UI or report; host env vars leaked to test subprocess | uploaded repo, host |
| Original code | silently modified by a patch | our own agents / LLM |
| Integrity of results | fabricated or stale "passed" claims; approval reused for a different patch | our own code / UI reruns |

## 2. Controls

### Ingestion (no code is ever executed here)
| Control | Limit / behaviour | Test |
|---|---|---|
| Archive size cap | `MAX_ZIP_BYTES = 20 MB` compressed | T-ZIP-04 |
| Uncompressed cap | `MAX_UNCOMPRESSED_BYTES = 100 MB` total, `MAX_FILE_BYTES = 2 MB` per file | T-ZIP-05 |
| File-count cap | `MAX_FILES = 2,000` entries | T-ZIP-06 |
| Compression-ratio cap | reject entry with ratio > 100 (zip-bomb heuristic) | T-ZIP-05 |
| Path traversal | reject absolute paths, drive letters, `..` components, backslash tricks; resolved path must be inside target (`Path.resolve().is_relative_to`) | T-ZIP-02 |
| Symlinks / special files | entries with symlink mode bits are rejected | T-ZIP-03 |
| Manual extraction | entries are written one by one with checks, never `extractall` | T-ZIP-01 |
| Ignore list | `.git`, `.venv`, `venv`, `env`, `__pycache__`, `node_modules`, `dist`, `build`, `.mypy_cache`, `.pytest_cache`, `.idea`, `.vscode`, binary files (NUL-byte sniff) | T-FLT-01 |
| Sensitive files | `.env*`, `*.pem`, `*.key`, `id_rsa*`, `*.p12`, `credentials*.json` are inventoried as "skipped (sensitive)" but content is never read or displayed | T-FLT-02 |
| Secret redaction | evidence snippets pass through a redactor (key-like literals → `"sk-…[REDACTED]"`) | T-RULE-06 |
| Original read-only | after extraction, files are `chmod` read-only and the snapshot is hashed; report re-hashes at the end to prove "original unchanged" | T-APP-03 |
| GitHub (optional) | only `https://github.com/<owner>/<repo>` matched by strict regex; downloads public zipball over HTTPS with timeout and size cap, then the same ZIP pipeline; no tokens used | T-GH-01 (if built) |

### Patching
| Control | Behaviour | Test |
|---|---|---|
| Proposal-only by default | Agent 4 produces a `PatchProposal`; nothing touches disk | T-APP-01 |
| Scope check (Agent 5) | edits may only touch the file(s) of the selected finding; paths re-validated inside working copy; no new files, no deletions, no binary content | T-APP-04 |
| Hash-bound approval | approval stores `patch_hash` + `base_snapshot_hash`; mismatched/stale/foreign approvals are refused | T-APR-01..03 |
| Fresh working copy | each approved patch is applied to a new copy of the original; original is never opened for writing | T-APP-02 |
| Original-file precondition | each `FileEdit.original_sha256` must match before writing | T-APR-03 |
| No VCS actions | no `git commit`/`push` code exists in the project | review |
| LLM cannot bypass | LLM output is only used as display text; it cannot create approvals, change state, or alter edits | T-LLM-01 |

### Test execution (Agent 5)
| Control | Behaviour |
|---|---|
| Separate process | `subprocess.Popen([sys.executable, "-I", "-B", "-m", "pytest", ...], shell=False)` — never `exec` in the Streamlit process |
| Timeout | `TEST_TIMEOUT_S = 60`; process tree killed on expiry → status **BLOCKED (timeout)** |
| Stripped environment | env contains only `PATH`, a throw-away `HOME`/`TMP`/`TEMP`/`TMPDIR` next to the working copy, `PYTHONHASHSEED=0`, `LANG=C.UTF-8` and `SYSTEMROOT` (Windows); no proxy vars, tokens or user variables. Bytecode writes are disabled with `-B`. `test_runner_env_is_stripped` proves a host secret variable does not reach the test process |
| Working directory | the per-run working copy (temporary), `-p no:cacheprovider`, `--rootdir` pinned |
| Resource limits (POSIX only) | `preexec_fn` sets `RLIMIT_CPU`, `RLIMIT_AS` (1 GB), `RLIMIT_FSIZE` (50 MB), `RLIMIT_NOFILE`; on Windows these are unavailable and the report says "timeout-only isolation" |
| No dependency install | uploaded `requirements.txt` is never installed; missing imports surface as test errors |
| Trust policy | runtime tests run automatically **only for the bundled sample repo**. For uploaded repos, runtime tests are **off by default**; the user must tick an explicit "I trust this code" checkbox, and the result is labelled "limited isolation (not a security sandbox)". Without opt-in, validation is static only → `PARTIALLY_VERIFIED` |

**Honest limitation:** a subprocess with a temp directory, stripped env and rlimits is *not* a security sandbox (no network or filesystem isolation). Proper isolation (container, VM, gVisor, nsjail) is future scope. This is stated in the UI, the report and the viva notes.

## 3. Failure handling

| Failure | Detected by | System behaviour | User sees |
|---|---|---|---|
| Corrupt / unsafe / oversized ZIP | `zip_loader` | run → `BLOCKED`, nothing extracted (partial extraction directory deleted) | specific reason (e.g. "entry `../evil.py` escapes workspace") |
| No README | Agent 1 | continue; doc gap recorded | "README missing" in doc gaps |
| No Python files | Planner | A2/A4/A5 marked *Not run* | structure-only report |
| File fails to parse (`SyntaxError`) | Agent 2 | file recorded as finding "Unparseable file" (R000, Confirmed by parser) and skipped by other rules | finding with line from `SyntaxError` |
| Rule crashes on odd code | Agent 2 | exception caught per rule × file, logged, analysis continues | warning in agent log |
| No fix strategy for a rule | Agent 4 | proposal not offered | "No automated fix available; manual remediation: …" |
| Critic rejects patch scope | Agent 5 | back to Agent 4 (counts as a retry) | critic issues listed |
| Stale approval | approval guard | refused, state unchanged | error banner |
| Syntax error after patch | Agent 5 | `FAILED`, retry path | compiler message |
| Tests fail after patch | Agent 5 | `VALIDATION_FAILED` → next strategy (needs new approval) | failing test names + output tail |
| Retries exhausted | Orchestrator | `BLOCKED`, escalate | all attempts and their results |
| Test timeout | sandbox runner | `BLOCKED (timeout)` | timeout message |
| pytest not installed / no tests | sandbox runner | `NOT_RUN` for tests → overall `PARTIALLY_VERIFIED` | explicit statement that runtime testing did not happen |
| Ollama unavailable / bad output | LLM adapter | fall back to deterministic text, log reason | "LLM unavailable — deterministic explanation shown" |
| Any unexpected exception | orchestrator wrapper | `BLOCKED`, traceback in log | error panel, never a silent success |

## 4. Controls added during the build (Phase 2–3)

| Control | Behaviour | Evidence |
|---|---|---|
| Network isolation (Linux) | the test run is wrapped in `unshare --net --map-root-user` when the kernel allows it; otherwise the report states "Network access is not blocked on this machine" | `sandbox_runner.network_isolation_available()`; shown in Validation Results |
| Path check at approval | `approval.record()` refuses an edit whose path would leave the workspace, before any file is touched | `test_traversal_edit_rejected` |
| Redacted outputs | diffs, test failure messages and reports go through the secret redactor; full file contents are not included in the JSON report | `test_secret_never_in_evidence`, `test_redaction` |
| Upload cap in the UI | `.streamlit/config.toml` sets `maxUploadSize = 20` (MB) so the upload widget matches `MAX_ZIP_BYTES` instead of Streamlit's 200 MB default | browser E2E screenshot `14_upload_untrusted_zip.png` |
| Windows parity | baseline confirmation matches OS-native traceback paths (`grades\stats.py`), so a finding is confirmed on Windows exactly as on Linux | `test_baseline_links_windows_style_traceback_paths`; Windows run in `docs/test-evidence/phase3_pytest_windows_python3.13.txt` |
| Untrusted upload in the real UI | uploading a ZIP without ticking "I trust this code" runs analysis only; no test process is started | browser E2E step "no baseline test run for untrusted code" |
| Malicious ZIP in the real UI | a `../../evil.py` entry is refused with a specific reason, nothing is extracted | browser E2E screenshot `15_upload_traversal_refused.png` |

### What is still not protected (stated in the UI, report and viva)

- The test subprocess can read files outside the working copy and, on Windows/macOS, use the network. It is **not** a security sandbox. Only run tests of code you trust.
- On Windows only the timeout is enforced (no CPU/memory/file-size limits).
- Static analysis is limited to 9 rules (+ optional pyflakes); a clean result is not a security guarantee.
