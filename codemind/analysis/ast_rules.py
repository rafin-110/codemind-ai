"""Deterministic Python AST rules R000-R009 (ARCHITECTURE.md section 5).

Each rule returns `RuleHit`s with exact line numbers. Rules only *parse* code; they
never import or execute it. A hit is a signal for review, not proof of a bug, and the
confidence level says how strong the signal is.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from codemind.models import Confidence, Severity


@dataclass(frozen=True)
class RuleInfo:
    rule_id: str
    title: str
    category: str
    severity: Severity
    confidence: Confidence
    why: str
    impact: str
    remediation: str
    validation: str


RULES: dict[str, RuleInfo] = {r.rule_id: r for r in [
    RuleInfo("R000", "File cannot be parsed", "Correctness", Severity.HIGH, Confidence.CONFIRMED,
             "Python could not parse this file, so it cannot be imported or run.",
             "Any code importing this module fails immediately.",
             "Fix the syntax error at the reported line.",
             "py_compile succeeds on the file."),
    RuleInfo("R001", "Possible division by zero", "Logic", Severity.HIGH, Confidence.POTENTIAL,
             "The denominator can be zero (e.g. an empty list) and there is no visible guard before the division.",
             "ZeroDivisionError crashes the caller on boundary input such as an empty list.",
             "Check the denominator first and either return a documented default or raise a clear ValueError.",
             "Run a test that calls the function with an empty / zero input and checks the documented behaviour."),
    RuleInfo("R002", "Exception silently swallowed", "Error handling", Severity.MEDIUM, Confidence.LIKELY,
             "A bare `except:` (or `except Exception: pass`) hides every error, including typos, "
             "KeyboardInterrupt and corrupted data.",
             "Failures turn into silent wrong results that are hard to debug.",
             "Catch only the exceptions you expect (e.g. OSError, ValueError) and handle or report them.",
             "Run existing tests; add a test that the expected error path still returns the fallback."),
    RuleInfo("R003", "Use of eval/exec", "Security", Severity.HIGH, Confidence.LIKELY,
             "`eval`/`exec` run arbitrary Python code contained in a string.",
             "If the string comes from a user or file, an attacker can run any command on the machine.",
             "Use `ast.literal_eval` for literals, or parse the input explicitly.",
             "Test that valid literal input still works and that code-like input is rejected."),
    RuleInfo("R004", "Mutable default argument", "Logic", Severity.MEDIUM, Confidence.LIKELY,
             "Default values are created once, so a default list/dict is shared between calls.",
             "Data leaks between calls: the second call sees values from the first.",
             "Use `None` as the default and create a new object inside the function.",
             "Test that two calls without the argument return independent results."),
    RuleInfo("R005", "Shell command execution", "Security", Severity.HIGH, Confidence.LIKELY,
             "`shell=True` / `os.system` pass a string to the shell, so spaces and special characters "
             "in variables are interpreted as shell syntax.",
             "Command injection and broken paths containing spaces.",
             "Pass the command as a list of arguments with `shell=False`.",
             "Test with a path containing spaces; review that no shell features were needed."),
    RuleInfo("R006", "Hard-coded secret", "Security", Severity.HIGH, Confidence.POTENTIAL,
             "A credential-like value is written directly in source code.",
             "Anyone with access to the code or its history gets the secret; rotating it needs a code change.",
             "Read the value from an environment variable or a secrets manager.",
             "Check the module still imports and the value is read from the environment."),
    RuleInfo("R007", "SQL built from string formatting", "Security", Severity.HIGH, Confidence.LIKELY,
             "The SQL text is built with f-strings / `%` / `+` / `.format`, so input becomes part of the query.",
             "SQL injection: input like `' OR '1'='1` changes the query; quotes in names break it.",
             "Use a parameterised query (`?` placeholders and a parameters tuple).",
             "Run the existing query tests and a test with a quote in the input."),
    RuleInfo("R008", "Unvalidated numeric input", "Input handling", Severity.MEDIUM, Confidence.LIKELY,
             "`int()`/`float()` is applied directly to `input()` with no error handling.",
             "Typing a non-number crashes the program with ValueError.",
             "Wrap the conversion in try/except ValueError and ask again or report a clear error.",
             "Manual or scripted test with non-numeric input."),
    RuleInfo("R009", "Comparison to None with ==", "Style", Severity.LOW, Confidence.LIKELY,
             "`== None` calls the object's __eq__, which can be overridden; PEP 8 requires `is None`.",
             "Usually harmless, but can give wrong answers for objects such as NumPy arrays.",
             "Use `is None` / `is not None`.",
             "Existing tests keep passing."),
]}


@dataclass
class RuleHit:
    rule_id: str
    line: int
    end_line: int
    symbol: str = ""
    detail: str = ""
    severity: Severity | None = None        # override of the rule default
    confidence: Confidence | None = None
    extra: dict = field(default_factory=dict)


_SECRET_NAME = re.compile(r"(key|secret|token|passw(or)?d|pwd|credential)", re.IGNORECASE)
_SUBPROCESS_FUNCS = {"run", "call", "Popen", "check_output", "check_call"}
_SQL_METHODS = {"execute", "executemany", "executescript"}


def _names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _is_call_to(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name


class _Analyzer(ast.NodeVisitor):
    def __init__(self) -> None:
        self.hits: list[RuleHit] = []
        self.func_stack: list[ast.AST] = []
        self.try_stack: list[ast.Try] = []
        self.module: ast.Module | None = None

    # -- scope tracking ---------------------------------------------------
    def visit_Module(self, node: ast.Module) -> None:
        self.module = node
        self.generic_visit(node)

    def _visit_func(self, node) -> None:
        self._check_mutable_defaults(node)
        self.func_stack.append(node)
        self.generic_visit(node)
        self.func_stack.pop()

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func

    def visit_Try(self, node: ast.Try) -> None:
        for handler in node.handlers:
            self._check_handler(handler)
        self.try_stack.append(node)
        for stmt in node.body:
            self.visit(stmt)
        self.try_stack.pop()
        for part in node.handlers + node.orelse + node.finalbody:
            self.visit(part)

    visit_TryStar = visit_Try

    @property
    def symbol(self) -> str:
        return getattr(self.func_stack[-1], "name", "") if self.func_stack else ""

    @property
    def scope(self) -> ast.AST:
        return self.func_stack[-1] if self.func_stack else self.module

    def _protected_by(self, exc_names: set[str]) -> bool:
        for t in self.try_stack:
            for h in t.handlers:
                if h.type is None:
                    return True
                types = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
                for ty in types:
                    if isinstance(ty, ast.Name) and ty.id in exc_names:
                        return True
        return False

    # -- R001 division -----------------------------------------------------
    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            self._check_division(node)
        self.generic_visit(node)

    def _check_division(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Mod) and isinstance(node.left, (ast.Constant, ast.JoinedStr)):
            return  # string formatting
        right = node.right
        if isinstance(right, ast.Name):
            var, kind = right.id, "name"
        elif _is_call_to(right, "len") and len(right.args) == 1 and isinstance(right.args[0], ast.Name):
            var, kind = right.args[0].id, "len"
        else:
            return
        if self._protected_by({"ZeroDivisionError", "ArithmeticError", "Exception", "BaseException"}):
            return
        for n in ast.walk(self.scope):
            if isinstance(n, (ast.If, ast.While, ast.Assert, ast.IfExp)) and n.lineno <= node.lineno:
                if var in _names_in(n.test):
                    return  # some guard mentions the denominator; assume it is handled
        self.hits.append(RuleHit("R001", node.lineno, node.end_lineno or node.lineno, self.symbol,
                                 f"denominator `{ast.unparse(right)}` is not checked for zero",
                                 extra={"var": var, "kind": kind, "denominator": ast.unparse(right)}))

    # -- R002 swallowed exceptions -----------------------------------------
    def _check_handler(self, h: ast.ExceptHandler) -> None:
        body_is_pass = all(isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
                           for s in h.body)
        broad = h.type is None or (isinstance(h.type, ast.Name) and h.type.id in ("Exception", "BaseException"))
        if h.type is None or (broad and body_is_pass):
            what = "bare `except:`" if h.type is None else f"`except {ast.unparse(h.type)}`"
            self.hits.append(RuleHit("R002", h.lineno, h.lineno, self.symbol,
                                     f"{what} {'with only `pass`' if body_is_pass else 'catches everything'}",
                                     severity=Severity.MEDIUM,
                                     extra={"bare": h.type is None, "body_is_pass": body_is_pass}))

    # -- calls: R003, R005, R007, R008 -------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        f = node.func
        if isinstance(f, ast.Name) and f.id in ("eval", "exec"):
            self._check_eval(node, f.id)
        if (isinstance(f, ast.Attribute) and f.attr in _SUBPROCESS_FUNCS
                and isinstance(f.value, ast.Name) and f.value.id == "subprocess"):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    self.hits.append(RuleHit("R005", node.lineno, node.end_lineno or node.lineno, self.symbol,
                                             f"`subprocess.{f.attr}(..., shell=True)`",
                                             extra={"call": f"subprocess.{f.attr}"}))
        if isinstance(f, ast.Attribute) and f.attr == "system" and isinstance(f.value, ast.Name) and f.value.id == "os":
            self.hits.append(RuleHit("R005", node.lineno, node.end_lineno or node.lineno, self.symbol,
                                     "`os.system(...)` runs a shell command", extra={"call": "os.system"}))
        if isinstance(f, ast.Attribute) and f.attr in _SQL_METHODS and node.args:
            q = node.args[0]
            dynamic = (isinstance(q, ast.JoinedStr) and any(isinstance(v, ast.FormattedValue) for v in q.values)) \
                or (isinstance(q, ast.BinOp) and isinstance(q.op, (ast.Add, ast.Mod))) \
                or (isinstance(q, ast.Call) and isinstance(q.func, ast.Attribute) and q.func.attr == "format")
            if dynamic:
                self.hits.append(RuleHit("R007", node.lineno, node.end_lineno or node.lineno, self.symbol,
                                         f"query passed to `.{f.attr}()` is built dynamically",
                                         extra={"query_kind": type(q).__name__}))
        if isinstance(f, ast.Name) and f.id in ("int", "float") and node.args and _is_call_to(node.args[0], "input"):
            if not self._protected_by({"ValueError", "Exception", "BaseException"}):
                self.hits.append(RuleHit("R008", node.lineno, node.end_lineno or node.lineno, self.symbol,
                                         f"`{f.id}(input(...))` without try/except ValueError"))
        self.generic_visit(node)

    def _check_eval(self, node: ast.Call, fname: str) -> None:
        from_input = False
        if node.args:
            arg = node.args[0]
            if _is_call_to(arg, "input"):
                from_input = True
            elif isinstance(arg, ast.Name):
                for n in ast.walk(self.scope):
                    if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == arg.id for t in n.targets):
                        if _is_call_to(n.value, "input"):
                            from_input = True
        self.hits.append(RuleHit(
            "R003", node.lineno, node.end_lineno or node.lineno, self.symbol,
            f"`{fname}()` on " + ("user input from `input()`" if from_input else "a dynamic string"),
            severity=Severity.CRITICAL if from_input else None,
            extra={"func": fname, "from_input": from_input}))

    # -- R004 mutable defaults ---------------------------------------------
    def _check_mutable_defaults(self, node) -> None:
        args = node.args
        positional = args.posonlyargs + args.args
        pairs = list(zip(positional[len(positional) - len(args.defaults):], args.defaults))
        pairs += [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is not None]
        for arg, default in pairs:
            mutable = isinstance(default, (ast.List, ast.Dict, ast.Set)) or (
                isinstance(default, ast.Call) and isinstance(default.func, ast.Name)
                and default.func.id in ("list", "dict", "set") and not default.args)
            if mutable:
                self.hits.append(RuleHit("R004", node.lineno, node.lineno, node.name,
                                         f"parameter `{arg.arg}` defaults to `{ast.unparse(default)}`",
                                         extra={"param": arg.arg, "default": ast.unparse(default)}))

    # -- R006 secrets --------------------------------------------------------
    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and len(node.value.value) >= 8:
            for t in node.targets:
                if isinstance(t, ast.Name) and _SECRET_NAME.search(t.id) and " " not in node.value.value:
                    self.hits.append(RuleHit("R006", node.lineno, node.end_lineno or node.lineno, self.symbol,
                                             f"`{t.id}` is assigned a literal credential-like string",
                                             extra={"name": t.id}))
        self.generic_visit(node)

    # -- R009 == None --------------------------------------------------------
    def visit_Compare(self, node: ast.Compare) -> None:
        operands = [node.left] + list(node.comparators)
        for i, op in enumerate(node.ops):
            if isinstance(op, (ast.Eq, ast.NotEq)):
                a, b = operands[i], operands[i + 1]
                if any(isinstance(x, ast.Constant) and x.value is None for x in (a, b)):
                    self.hits.append(RuleHit("R009", node.lineno, node.end_lineno or node.lineno, self.symbol,
                                             f"`{ast.unparse(node)}` uses {'==' if isinstance(op, ast.Eq) else '!='} with None"))
        self.generic_visit(node)


def run_rules(tree: ast.Module) -> list[RuleHit]:
    analyzer = _Analyzer()
    analyzer.visit(tree)
    # one hit per (rule, line)
    seen, unique = set(), []
    for h in sorted(analyzer.hits, key=lambda h: (h.line, h.rule_id)):
        if (h.rule_id, h.line) not in seen:
            seen.add((h.rule_id, h.line))
            unique.append(h)
    return unique


def run_pyflakes(path: str, source: str) -> list[RuleHit] | None:
    """Optional extra checks. Returns None when pyflakes is not installed."""
    try:
        from pyflakes import api, messages
    except ImportError:
        return None

    class _Collector:
        def __init__(self):
            self.msgs = []

        def unexpectedError(self, *_):  # noqa: N802 - pyflakes API
            pass

        def syntaxError(self, *_):  # noqa: N802
            pass

        def flake(self, msg):
            self.msgs.append(msg)

    rep = _Collector()
    api.check(source, path, rep)
    hits = []
    for m in rep.msgs:
        if isinstance(m, messages.UndefinedName):
            hits.append(RuleHit("PF01", m.lineno, m.lineno, "", m.message % m.message_args,
                                severity=Severity.HIGH, confidence=Confidence.LIKELY))
    return hits


RULES["PF01"] = RuleInfo("PF01", "Undefined name (pyflakes)", "Correctness", Severity.HIGH, Confidence.LIKELY,
                         "The name is used but never defined or imported in this module.",
                         "NameError when this line runs.",
                         "Define or import the name, or fix the typo.",
                         "Import the module in tests and exercise the line.")
