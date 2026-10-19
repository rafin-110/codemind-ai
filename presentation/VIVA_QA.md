# CodeMind AI — Viva Q&A

Short, honest answers. File references point to where you can show proof.

## Concept

**Q: Why is this "agentic" and not just a script or a chatbot?**
A planner builds a task plan from what the repo contains (no tests → baseline skipped; untrusted upload → tests not run). Five agents with separate roles write structured results into shared state. The critic can send a proposal back, and a failed validation feeds its test output to the improvement agent, which then picks a different strategy. A state machine controls all of it, and every transition is logged with a reason (`codemind/orchestrator/`, Agent Workflow view).

**Q: Where is the AI? There's no LLM call by default.**
Deliberately. The brief said no paid APIs and never fabricate results. The agents' reasoning is deterministic (AST analysis, ranking, strategy selection from test feedback), so every claim is reproducible. An LLM can be plugged in through `codemind/llm/adapter.py` (Ollama supported), but only to reword explanations. It can't approve, edit or change state. Future scope: LLM-generated fixes behind the same gates.

**Q: Why code review as the domain?**
Code claims can be checked: parsed, diffed and tested. So an agent's output can be backed by evidence instead of trust, which is exactly what review of AI-generated code needs.

## Design

**Q: How do you guarantee the original code is never modified?**
Files are made read-only and hashed at ingest. Patches only apply to a fresh working copy. Approval is bound to the patch hash and the source hash, and the original is re-hashed after every validation. This is shown in the UI and tested (`test_approve_changes_only_the_copy`, `test_reject_leaves_original_and_creates_no_copy`).

**Q: What stops an old approval being reused for a different patch?**
Approval stores the exact patch hash and the base snapshot hash. A wrong hash, an older approval, a tampered proposal or a changed original are all refused (4 tests under T-APR).

**Q: What does "Confirmed" mean?**
During analysis, the project's own tests run on an untouched copy. If a failing test's traceback points at the finding's exact `file:line`, the finding is Confirmed. Otherwise it is Likely or Potential.

**Q: When is a validation "Passed"?**
The patched file compiles, the rule no longer matches, there are no new failures compared with the baseline, and the tests linked to the finding now pass. Failures that already existed are allowed but listed, so an unrelated broken test doesn't block a correct fix.

**Q: Why no database?**
It's a single-user PoC. State lives in one typed context per session and is exported as JSON/Markdown reports (`ARCHITECTURE.md` §7).

## Security

**Q: Isn't running uploaded tests dangerous?**
Yes, so: analysis never executes code. Tests only run for the bundled sample, or if the user explicitly ticks "I trust this code". They run in a separate process with a timeout, stripped environment, isolated mode, and on Linux resource limits and no network. We say clearly that this is **not** a sandbox. Containers are future work.

**Q: How do you handle malicious ZIPs?**
Size, total-size, file-count and compression-ratio caps, no absolute or `..` paths, no symlinks, manual per-entry extraction, and sensitive files never read. 17 tests cover this, and the browser test uploads a `../../evil.py` archive to show the refusal.

## Results and honesty

**Q: 9/9 detection, isn't that too good?**
It's on a synthetic sample we wrote with planted issues, so it shows the rules work as designed, not real-world accuracy. The ground truth was located by text search, independently of the rule engine. Real-world evaluation is future scope.

**Q: Did testing find anything real?**
Yes. On Windows, 4 tests failed because pytest prints `grades\stats.py` with a backslash, so findings weren't confirmed and the retry demo broke. The Linux runs couldn't show it. Fixed in one line, with a regression test (`TESTING_REPORT.md` §2).

**Q: Why does a "Passed" fix still show 1 failed test?**
That test belongs to F-004 and already fails on the original. It's listed as pre-existing and passes once F-004 is fixed.

**Q: What are the main limitations?**
9 rules, Python only, no cross-function analysis, template fixes for 8 rules, validation only as strong as the repo's tests, not a real sandbox (timeout-only on Windows), single user (`LIMITATIONS_AND_FUTURE_SCOPE.md`).

**Q: What would you build next?**
An LLM reviewer behind the same critic/approval/test gates, PR integration that comments and suggests but never pushes, container sandboxing, and Bandit/Semgrep/Ruff as tools for the risk agent.

## Technical quick answers

- **Stack:** Python 3.11+, Streamlit, `ast`, `difflib`, `pytest`. No paid API, works offline.
- **Why Streamlit:** fastest way to a working, demo-able UI. The logic (`codemind/`) never imports streamlit, and a test checks that.
- **Why not LangGraph:** a 12-state explicit state machine is simpler to test and explain (`ARCHITECTURE.md` §9).
- **Max retries:** 2, then BLOCKED and escalated to the developer.
- **Test count:** 105 (104 + 1 optional pyflakes test).
