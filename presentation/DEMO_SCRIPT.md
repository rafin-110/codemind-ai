# CodeMind AI — 5-minute presentation and demo script

Timing: **30s / 45s / 2m / 60s / 45s** = 5:00. Setup steps are in `DEMO_CHECKLIST.md`. App running at http://localhost:8501, PPT on slide 1.

## 0:00–0:30 · Problem (slide 1)

> "More and more code is written by AI, and people accept it because it runs. But it hides bugs and security holes, like eval on user input or SQL built from strings. Code review is how teams catch this, but it doesn't scale, and a student has no reviewer at all. CodeMind AI is an agentic code review assistant for exactly that."

## 0:30–1:15 · Solution and agents (slides 2–4)

> "Each existing tool fails in one way. Linters are terse, chatbots rewrite whole files, and nothing proves a fix works. Our answer is one loop: analyse, explain with evidence, compare options, ask the human, apply to a copy, validate with real tests, report."
>
> (slide 3) "A planner runs five agents over one shared state: understanding, bug & risk, an advisor, code improvement, and a critic/validator. A state machine enforces that the **only** way to change code is human approval."
>
> (slide 4) "The original upload is read-only and hashed. Patches go to a separate copy. If validation fails, it loops back with a new strategy, at most twice, then stops."

## 1:15–3:15 · Live demo (browser)

| Time | Do | Say |
|---|---|---|
| 1:15 | Upload & Explorer → **Load sample repository** → **Run analysis** | "A synthetic student-grades app with planted issues. The agents analyse it, and nothing is executed except its own tests on an untouched copy." |
| 1:35 | Agent Workflow | "Here's the plan, every state change with a reason, and the agent log." |
| 1:50 | Findings → **F-004** | "Division by zero, marked **Confirmed**, because the project's own test fails on this exact line. Each finding has evidence, why, impact, a fix and how we will validate it." |
| 2:10 | Findings → F-001 → ask for fix → **Reject** | "A minimal diff for the eval issue. I reject it, and the original is untouched with no copy made. The human is in control." |
| 2:30 | F-004 → ask for fix → **Approve** | "Strategy 1 returns 0.0. Watch: it **fails** a real test, which expects an exception. The agent reads that failure and proposes a different strategy." |
| 2:50 | **Approve** again → Validation Results | "9 of 9 tests pass, and the original was re-hashed unchanged. Limitations are printed right here: not a sandbox, tests don't prove bug-free." |
| 3:05 | Download Markdown report | "Everything is exported as a report." |

## 3:15–4:15 · Validation and results (slide 6)

> "All numbers are real runs: 105 automated tests pass on Windows, plus a browser end-to-end test in Chrome. On the sample, 9 of 9 planted issues are found at the exact line with no false positives, and 8 of 9 fixes validate. The ninth deliberately has no auto-fix. Testing also caught a real bug: on Windows, pytest prints backslash paths, so the confirmation broke. We fixed it and added a regression test."

## 4:15–5:00 · Limitations, future, close (slides 7–8)

> "Limits: nine rules, Python only, template fixes, and test runs are not a true sandbox. Our sample is synthetic, so 9 of 9 isn't real-world accuracy. Next steps: an LLM reviewer kept behind the same critic, approval and test gates, pull-request integration, and container sandboxing. In short: understand, show evidence, compare, let the human approve, and prove it. Thank you."

**If the app fails:** go to `docs/screenshots/phase3/` and show 03 → 06 → 09 → 11 → 12 with the same lines.
