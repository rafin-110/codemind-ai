# CodeMind AI — Project Plan

> **An Agentic AI Code Review Assistant for Understanding, Debugging, and Improving AI-Generated Code**
> Domain: Code Review (Software Development and Developer Productivity) · University CA-3 PoC
> Status: **Phase 1 (design) complete, awaiting approval for Phase 2.** Nothing in this file describes implemented behaviour yet.

---

## 1. Problem statement (CA-3 deliverable 1)

Students, beginners and "vibe coders" increasingly ship code produced by AI assistants that they did not write and often do not fully understand. The generated code usually *runs*, so it gets accepted, but it can hide:

- logic defects that only show up on boundary inputs (e.g. dividing by an empty list's length),
- swallowed exceptions that turn crashes into silent wrong answers,
- security weaknesses (`eval` on user input, SQL built with f-strings, `shell=True`, hard-coded keys),
- maintainability problems (mutable default arguments, duplicated logic, unclear module boundaries).

Existing tools either **explain** code (chat assistants, with no evidence trail and a tendency to rewrite whole files) or **detect** problems (linters, with terse messages a beginner cannot act on). Neither keeps the developer in control of *what changes and why*, and neither proves that a proposed fix actually works.

**Problem:** developers need a way to understand an unfamiliar (often AI-generated) codebase, see evidence-backed explanations of its risks, compare fix options, and accept changes only after reviewing them and seeing real test results.

### Domain justification

- **Code review** is the standard quality gate before code is accepted, but it does not scale to the volume of AI-generated code: human reviewers are slow and inconsistent, and a beginner has no reviewer at all. CodeMind AI acts like a reviewer would. It reads the project, comments on specific lines with evidence and severity, suggests alternatives, and proposes a minimal change. The human still makes the accept/reject decision, as in a normal pull-request review.
- Software development is a domain where outputs are **verifiable**: code can be parsed, diffed and tested. That makes it a good fit for an agentic system that must ground its claims in tool results rather than free text.
- AI-assisted coding is now mainstream in education and industry, so "understand before you trust" is a real and growing need.
- The domain allows a fully **offline, free** PoC (Python `ast`, `difflib`, `pytest`), which satisfies the "no paid API" constraint without faking anything.

## 2. Existing challenges vs. proposed solution (CA-3 deliverable 2)

| Existing challenge | Effect on the developer | CodeMind AI response |
|---|---|---|
| AI-generated code accepted without understanding | Hidden bugs and architecture debt | Repository Understanding Agent explains structure, entry points and dependencies with file/line citations |
| Linters give terse, context-free warnings | Beginners ignore or misread them | Each finding carries evidence, "why it matters", impact, remediation and a validation method |
| Chat assistants rewrite code wholesale | Unreviewable changes, regressions | Code Improvement Agent proposes **minimal** single-finding patches shown as a unified diff |
| Fixes are applied without proof | "Fixed" code still fails | Critic & Validation Agent runs syntax checks and real `pytest` runs on an isolated copy; results are reported as Passed / Failed / Not run / Blocked / Partially verified |
| Tools act without consent | Loss of control, accidental damage | Hard human-approval gate tied to the exact patch hash and source hash; original files are never written |
| Only one "answer" is offered | No understanding of trade-offs | Solution & Architecture Advisor compares current vs. alternative approaches, including "keep the current approach" when it is appropriate |

**Proposed solution:** a Streamlit application with a Planner/Orchestrator and five specialised agents that follows the core loop

**ANALYZE → EXPLAIN WITH EVIDENCE → COMPARE SOLUTIONS → REQUEST HUMAN APPROVAL → APPLY APPROVED PATCH TO A COPY → VALIDATE → REPORT.**

## 3. Smallest reliable scope that satisfies every CA-3 criterion

### In scope (Phase 2 will build these)

| # | Capability | Real / Mock / Optional |
|---|---|---|
| S1 | ZIP upload, safe extraction into a controlled workspace | **Real** |
| S2 | Bundled synthetic sample repo (`samples/student_grades_app`) with intentionally inserted, documented bugs and its own pytest suite | **Real** (synthetic data, clearly labelled) |
| S3 | README / metadata parsing, directory tree, technology detection | **Real** |
| S4 | Python AST rule engine (9 rules, see ARCHITECTURE §5) with file + line evidence | **Real**, deterministic |
| S5 | Finding prioritisation (severity × confidence) | **Real**, deterministic |
| S6 | Alternative-solution comparison from a curated rule → alternatives knowledge base | **Real** deterministic templates; optional LLM rewording is labelled |
| S7 | Patch proposal for a selected finding, unified diff, affected files, suggested tests | **Real** deterministic AST/text transforms |
| S8 | Approval / rejection bound to patch hash + source hash, stale-approval invalidation | **Real** |
| S9 | Patch applied only to an isolated working copy, path and scope checks | **Real** |
| S10 | Validation: `py_compile` syntax check + `pytest` in a subprocess with timeout, stripped env, resource limits | **Real** (runtime tests default to the bundled sample only, see SECURITY_PLAN) |
| S11 | Bounded retry: failed validation → next fix strategy → re-approval (max 2 retries) → BLOCKED | **Real** |
| S12 | Agent execution log, workflow state view, downloadable JSON/Markdown report | **Real** |
| S13 | Optional local LLM (Ollama) adapter for explanation wording only | **Optional**; app fully works without it; a `MockLLM` that returns the deterministic text is the default and is labelled as such |
| S14 | Public GitHub URL input (downloads the zipball, then the S1 pipeline) | **Optional / stretch**; built only if S1–S12 are green |

### Out of scope (documented as future work)

Multi-language analysis beyond Python (non-Python files are inventoried, not analysed), private repos/auth, automatic commits or pushes (never), container/VM sandboxing, persistent multi-user storage, measured productivity claims.

## 4. Assumptions

- The examiner demo runs on a laptop with Python 3.11+ (developer machine is Windows; the cloud build environment is Linux/Python 3.13). The design avoids OS-specific behaviour except the optional POSIX `resource` limits, which degrade gracefully on Windows (timeout still enforced, limitation reported in the UI).
- The bundled synthetic repo is the primary demo input; it is written by us, so running its tests is acceptable. Arbitrary uploads are treated as untrusted.
- No internet is required at demo time (GitHub and Ollama are optional).

## 5. Deliverables and where they live

See `CA3_REQUIREMENT_TRACEABILITY.md` for the full requirement → file → feature → verification mapping. Phase-by-phase work is in `DEVELOPMENT_PLAN.md`; live status in `PROJECT_STATUS.md`.
