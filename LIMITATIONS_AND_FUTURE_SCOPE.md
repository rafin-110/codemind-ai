# CodeMind AI — Limitations and Future Scope (CA-3 deliverable 6)

## 1. Limitations (as of the final build)

### Analysis
| Limitation | Effect | Where it shows |
|---|---|---|
| Only 9 deterministic AST rules (R001–R009) plus R000 (unparseable file) and optional pyflakes | Many bug classes are invisible: wrong business logic, race conditions, off-by-one errors, performance problems, most type errors | "no rule matched; this is not proof of correctness" in the decision log |
| Python only | Other languages are listed in the tree but never analysed | Explorer view |
| Rules are pattern-based and intra-procedural | Data flow across functions is not tracked. R001 may flag a division that is safe because the caller guards it (a false positive), and miss one where the zero comes from another module | Confidence is "Likely"/"Potential" unless a real test confirms it |
| Evaluated on a synthetic sample written by us | 9/9 detection shows the rules work as designed. It is **not** a measure of real-world precision or recall | `TESTING_REPORT.md` §5 |

### Fixes
| Limitation | Effect |
|---|---|
| Fixes are deterministic templates (1–2 strategies per rule) | No fix for anything outside the 8 auto-fixable rules. R008 deliberately has no automatic patch |
| One finding per patch | Related findings must be fixed one after another, each with its own approval |
| Validation is only as good as the repo's tests | If a repo has no test for the behaviour, a patch can pass and still be wrong. The report says "Passing tests and static checks do not prove the code is bug-free" |

### Explanations and the "AI" part
| Limitation | Effect |
|---|---|
| Default explanations come from a curated knowledge base (labelled "Mock LLM") | Wording is repetitive across projects, though it is always grounded in real file/line evidence |
| Optional Ollama is used only to reword explanations | It was tested against a fake local server, not a real model. It never decides, approves or edits code |
| The "agents" are deterministic Python components coordinated by a planner and a state machine | Behaviour is reproducible and auditable, but the agents do not reason freely like an LLM agent would. This was a deliberate trade-off for a no-paid-API, never-fabricate PoC |

### Security and execution
| Limitation | Effect |
|---|---|
| Tests run in a subprocess, **not** a security sandbox | Test code can read files outside the working copy. That is why uploads need an explicit "I trust this code" tick |
| Windows: only a timeout is enforced | No CPU/memory/file-size limits and no network block on Windows. Linux gets rlimits and `unshare --net` when available |
| Uploaded dependencies are never installed | Tests of a project that needs extra packages fail with import errors (reported, not hidden) |

### Product
| Limitation | Effect |
|---|---|
| Single user, in-memory session state, no database | Reloading the browser tab starts a new run. Downloaded reports are the record |
| No GitHub URL input, no private repos, no PR integration | ZIP upload only |
| Streamlit UI | Good for a PoC demo, not a production review tool |

## 2. Future scope

Ordered by value for a real code-review workflow.

1. **LLM-backed reviewer with guardrails.** Use a local or hosted model to explain findings and propose fixes beyond the templates, but keep the current guardrails: evidence must cite real lines, every patch goes through the critic, human approval and a real test run. The existing `llm/adapter.py` interface is the plug-in point.
2. **Pull-request integration.** Run as a GitHub/GitLab check: comment on changed lines, suggest patches as review suggestions, and never push. This is where "code review" happens in practice.
3. **Real sandboxing.** Run tests in a container or microVM (Docker with no network, gVisor, Firecracker) so uploaded code can be tested safely on any OS.
4. **More languages and rules.** Integrate established analysers (Bandit, Semgrep, Ruff for Python; ESLint for JS) as tools for the Bug & Risk agent, and keep the evidence, confidence and approval pipeline the same.
5. **Inter-procedural analysis.** Track values across functions to cut false positives such as guarded divisions.
6. **Test generation.** When a repo has no test for a finding, have the agent propose a failing test first (also needing approval), then the fix.
7. **Measured evaluation.** Run on a labelled set of real repositories (e.g. known CVE fixes or bug datasets) and report precision, recall and fix success rate.
8. **Persistence and teams.** Store runs and decisions in a database for audit trails and multi-user review.
9. **GitHub URL input.** Public repos via zipball, through the same safe ZIP pipeline (designed in `SECURITY_PLAN.md`, not built).
