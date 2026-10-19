"""Curated knowledge base used by the Solution & Architecture Advisor.

Each entry compares the current approach with realistic alternatives. The advisor
fills in project-specific facts (function name, file, whether tests exist) and may
conclude that the current approach should be kept.
"""

from __future__ import annotations

from codemind.models import Alternative

A = Alternative

KB: dict[str, dict] = {
    "R000": {
        "current": "The file contains a syntax error and cannot be imported.",
        "alternatives": [
            A("Fix the syntax error in place", ("Smallest change", "Restores importability"), ("Needs a human to know the intent",),
              "Low", "Low", "Improves", "No effect"),
        ],
        "recommended": "Fix the syntax error in place",
        "rationale": "There is no design choice here: unparseable code cannot run.",
    },
    "R001": {
        "current": "`{symbol}()` divides by `{denominator}` without checking for zero.",
        "alternatives": [
            A("Return a neutral default (e.g. 0.0) for empty/zero input",
              ("Callers never crash", "Keeps the return type"),
              ("Silently hides a likely caller mistake", "0.0 can be mistaken for a real average"),
              "Low", "Low", "Neutral", "No measurable cost"),
            A("Raise a clear ValueError for empty/zero input",
              ("Fails fast with a readable message", "Matches Python's own `statistics.mean([])` behaviour"),
              ("Every caller must handle the error",),
              "Low", "Low", "Improves", "No measurable cost"),
            A("Return None (Optional result)",
              ("Explicit 'no value' signal",),
              ("Callers that format or add the result will crash later with a less clear error",),
              "Low", "Medium (type changes)", "Worse without type hints", "No measurable cost"),
            A("Use statistics.mean from the standard library",
              ("Well tested", "Raises StatisticsError on empty data"),
              ("Changes the exception type callers see",),
              "Low", "Low", "Improves", "Slightly slower for large lists"),
        ],
        "recommended": "Guard the denominator; prefer raising ValueError unless the project's tests or docs specify a default",
        "rationale": "Both a default and an exception are valid designs; the project's own tests are the "
                     "best evidence of intended behaviour, so the validator's test run decides between them.",
    },
    "R002": {
        "current": "`{symbol}()` catches every exception and continues silently.",
        "alternatives": [
            A("Catch only expected exceptions (OSError, ValueError) and keep the fallback",
              ("Real bugs still surface", "Expected failures keep current behaviour"),
              ("Must know which errors are expected",), "Low", "Low", "Improves", "No effect"),
            A("Log the error, then return the fallback",
              ("Failures become visible in logs",), ("Still hides programming errors from callers",),
              "Low", "Low", "Improves", "No effect"),
            A("Let the exception propagate",
              ("Simplest; caller decides",), ("Changes behaviour for callers that relied on the fallback",),
              "Low", "Low", "Improves", "No effect"),
        ],
        "recommended": "Catch only expected exceptions (OSError, ValueError) and keep the fallback",
        "rationale": "It removes the risk while keeping the function's documented fallback behaviour.",
    },
    "R003": {
        "current": "`{symbol}()` evaluates a string as Python code with `eval`.",
        "alternatives": [
            A("ast.literal_eval", ("Accepts Python literals only", "One-line change"),
              ("Still accepts any literal type, so the result must be validated",), "Low", "Low", "Improves", "No effect"),
            A("Explicit parsing (e.g. split on commas, float() each item)",
              ("Strictest validation", "Clear error messages"), ("More code",), "Medium", "Medium", "Improves", "No effect"),
            A("json.loads", ("Standard format",), ("Different syntax from Python lists for users",),
              "Low", "Low", "Improves", "No effect"),
        ],
        "recommended": "ast.literal_eval",
        "rationale": "It removes code execution with the smallest interface change; stricter parsing can follow.",
    },
    "R004": {
        "current": "`{symbol}()` uses a mutable object as a default argument value.",
        "alternatives": [
            A("None sentinel and create the object inside the function",
              ("Standard Python idiom", "Each call gets a fresh object"), ("Two extra lines",),
              "Low", "Low", "Improves", "No effect"),
            A("Use an immutable default (tuple) and copy", ("No sentinel",), ("Changes the type",),
              "Low", "Low", "Neutral", "No effect"),
        ],
        "recommended": "None sentinel and create the object inside the function",
        "rationale": "It is the idiomatic fix and keeps the public signature compatible.",
    },
    "R005": {
        "current": "`{symbol}()` builds a shell command string and runs it with the shell.",
        "alternatives": [
            A("Pass an argument list with shell=False", ("No shell interpretation", "Paths with spaces work"),
              ("Shell features (pipes, globs) are unavailable",), "Low", "Low", "Improves", "Slightly faster"),
            A("Use a platform API (e.g. os.startfile / webbrowser) instead of a shell",
              ("No subprocess at all",), ("Platform-specific",), "Low", "Low", "Improves", "No effect"),
            A("shlex.quote the variables", ("Keeps the shell",), ("Easy to get wrong; still a shell",),
              "Low", "Low", "Neutral", "No effect"),
        ],
        "recommended": "Pass an argument list with shell=False",
        "rationale": "Nothing in the command needs shell features, so the shell only adds risk.",
    },
    "R006": {
        "current": "`{name}` is hard-coded in source.",
        "alternatives": [
            A("Read from an environment variable", ("No secret in code or git history",),
              ("Must be set in each environment",), "Low", "Low", "Improves", "No effect"),
            A("Secrets manager / keyring", ("Central rotation and audit",), ("Extra dependency and setup",),
              "Medium", "Medium", "Improves", "Network call at start-up"),
            A("Keep it in code (only if it is a public, non-secret identifier)",
              ("No change",), ("Unsafe if it is a real credential",), "None", "None", "Neutral", "No effect"),
        ],
        "recommended": "Read from an environment variable",
        "rationale": "It is the smallest change that removes the value from source; the leaked value must also be rotated.",
    },
    "R007": {
        "current": "`{symbol}()` builds SQL by inserting values into the query text.",
        "alternatives": [
            A("Parameterised query with placeholders", ("Prevents injection", "Handles quotes in data"),
              ("None for this case",), "Low", "Low", "Improves", "Same or faster (statement caching)"),
            A("ORM / query builder (e.g. SQLAlchemy)", ("Safe by default for larger apps",),
              ("New dependency; large change for a small app",), "High", "High", "Mixed", "Some overhead"),
            A("Escape quotes manually", ("No API change",), ("Fragile; easy to miss cases",),
              "Low", "Low", "Worse", "No effect"),
        ],
        "recommended": "Parameterised query with placeholders",
        "rationale": "The DB driver already supports it; an ORM would be an unnecessary rewrite for this project.",
    },
    "R008": {
        "current": "`{symbol}()` converts raw user input to a number with no error handling.",
        "alternatives": [
            A("try/except ValueError with a re-prompt loop", ("Friendly UX",), ("Interactive loop is harder to test",),
              "Low", "Low", "Improves", "No effect"),
            A("Validate and raise a clear error", ("Simple and testable",), ("Program still stops",),
              "Low", "Low", "Improves", "No effect"),
            A("Use a CLI parser (argparse) instead of input()", ("Validation built in", "Scriptable"),
              ("Changes how users run the tool",), "Medium", "Medium", "Improves", "No effect"),
        ],
        "recommended": "try/except ValueError with a re-prompt loop",
        "rationale": "Keeps the interactive design; the right UX depends on the developer, so no automatic patch is offered.",
    },
    "R009": {
        "current": "`{symbol}()` compares with None using `==`.",
        "alternatives": [
            A("Use `is None`", ("PEP 8 idiom", "Cannot be fooled by custom __eq__"), ("None",),
              "Low", "Low", "Improves", "Marginally faster"),
            A("Keep `== None`", ("No change",), ("Lint warning; wrong for some types (e.g. NumPy arrays)",),
              "None", "None", "Neutral", "No effect"),
        ],
        "recommended": "Use `is None`",
        "rationale": "Low risk either way; with plain numbers the current code works, so this is optional polish.",
        "keep_current_when": "values are plain ints/floats",
    },
    "PF01": {
        "current": "A name is used but not defined.",
        "alternatives": [
            A("Define or import the name", ("Fixes NameError",), ("Requires knowing the intent",),
              "Low", "Low", "Improves", "No effect"),
        ],
        "recommended": "Define or import the name",
        "rationale": "Undefined names fail at runtime; there is no reasonable alternative.",
    },
}
