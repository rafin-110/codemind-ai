"""Rule-specific, minimal fix strategies.

Each strategy takes the original source of ONE file plus the finding and returns
new source for that same file. Strategies locate code with `ast` positions and
edit only the affected lines. If a pattern is not one we can fix safely, they
raise `NoFix` instead of guessing.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Callable

from codemind.models import Finding


class NoFix(Exception):
    """This finding cannot be fixed automatically and safely."""


@dataclass(frozen=True)
class Strategy:
    name: str
    description: str
    apply: Callable[[str, Finding], str]
    feedback_keywords: tuple[str, ...] = ()   # used to pick this strategy after a failed validation


# ----------------------------------------------------------------- source helpers

def _line_offsets(source: str) -> list[int]:
    offsets, pos = [0], 0
    for line in source.splitlines(keepends=True):
        pos += len(line)
        offsets.append(pos)
    return offsets


def _char_index(source: str, lineno: int, col_byte: int) -> int:
    """Convert ast (1-based line, UTF-8 byte column) to an index in `source`."""
    lines = source.splitlines(keepends=True)
    line = lines[lineno - 1]
    col_chars = len(line.encode("utf-8")[:col_byte].decode("utf-8", errors="ignore"))
    return _line_offsets(source)[lineno - 1] + col_chars


def replace_node(source: str, node: ast.AST, new_text: str) -> str:
    start = _char_index(source, node.lineno, node.col_offset)
    end = _char_index(source, node.end_lineno, node.end_col_offset)
    return source[:start] + new_text + source[end:]


def insert_lines(source: str, before_line: int, text: str) -> str:
    lines = source.splitlines(keepends=True)
    if not text.endswith("\n"):
        text += "\n"
    lines.insert(before_line - 1, text)
    return "".join(lines)


def indent_of(source: str, lineno: int) -> str:
    line = source.splitlines()[lineno - 1]
    return line[: len(line) - len(line.lstrip())]


def ensure_import(source: str, module: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Import) and any(a.name == module and a.asname is None for a in node.names):
            return source
    # insert after the module docstring and any __future__ imports, before other imports
    insert_at = 1
    for node in tree.body:
        is_doc = isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
        is_future = isinstance(node, ast.ImportFrom) and node.module == "__future__"
        if is_doc or is_future:
            insert_at = node.end_lineno + 1
            continue
        break
    text = f"import {module}\n"
    lines = source.splitlines(keepends=True)
    # keep a blank line after the docstring if there was one
    if insert_at - 1 < len(lines) and lines[insert_at - 1].strip() == "" and insert_at > 1:
        insert_at += 1
    return insert_lines(source, insert_at, text)


def _function(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _statement_at(scope: ast.AST, line: int) -> ast.stmt:
    """Innermost statement containing `line`."""
    best = None
    for node in ast.walk(scope):
        if isinstance(node, ast.stmt) and node is not scope and node.lineno <= line <= (node.end_lineno or node.lineno):
            if best is None or (node.lineno >= best.lineno and (node.end_lineno or 0) <= (best.end_lineno or 0)):
                best = node
    if best is None:
        raise NoFix("could not locate the statement")
    return best


def _first_body_line(func) -> int:
    body = func.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str) and len(body) > 1:
        return body[1].lineno
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        raise NoFix("function has only a docstring")
    return body[0].lineno


def _node_at(tree: ast.AST, line: int, kind: type, pred=lambda n: True):
    for node in ast.walk(tree):
        if isinstance(node, kind) and node.lineno == line and pred(node):
            return node
    raise NoFix(f"no {kind.__name__} found at line {line}")


# ------------------------------------------------------------------- strategies

def _division_guard(source: str, f: Finding, body: str) -> str:
    if not f.symbol:
        raise NoFix("division at module level; guard must be written by hand")
    tree = ast.parse(source)
    func = _function(tree, f.symbol)
    if func is None:
        raise NoFix("enclosing function not found")
    stmt = _statement_at(func, f.line)
    var, kind = f.extra.get("var"), f.extra.get("kind")
    cond = f"not {var}" if kind == "len" else f"{var} == 0"
    ind = indent_of(source, stmt.lineno)
    guard = f"{ind}if {cond}:\n{ind}    {body}\n"
    return insert_lines(source, stmt.lineno, guard)


def r001_default(source: str, f: Finding) -> str:
    return _division_guard(source, f, "return 0.0")


def r001_raise(source: str, f: Finding) -> str:
    var, kind = f.extra.get("var"), f.extra.get("kind")
    msg = f"{var} must not be empty" if kind == "len" else f"{var} must not be zero"
    return _division_guard(source, f, f'raise ValueError("{msg}")')


def r002_narrow(source: str, f: Finding) -> str:
    tree = ast.parse(source)
    handler = _node_at(tree, f.line, ast.ExceptHandler)
    line = source.splitlines(keepends=True)[handler.lineno - 1]
    stripped = line.lstrip()
    if handler.type is None:
        if not stripped.startswith("except:"):
            raise NoFix("unexpected except clause layout")
        new_line = line.replace("except:", "except (OSError, ValueError):", 1)
    else:
        if handler.name:
            raise NoFix("handler binds the exception; review manually")
        new_line = line.replace(f"except {ast.unparse(handler.type)}:", "except (OSError, ValueError):", 1)
        if new_line == line:
            raise NoFix("unexpected except clause layout")
    lines = source.splitlines(keepends=True)
    lines[handler.lineno - 1] = new_line
    return "".join(lines)


def r003_literal_eval(source: str, f: Finding) -> str:
    if f.extra.get("func") != "eval":
        raise NoFix("exec() has no safe drop-in replacement")
    tree = ast.parse(source)
    call = _node_at(tree, f.line, ast.Call, lambda n: isinstance(n.func, ast.Name) and n.func.id == "eval")
    if len(call.args) != 1 or call.keywords:
        raise NoFix("eval called with globals/locals; review manually")
    new = replace_node(source, call.func, "ast.literal_eval")
    return ensure_import(new, "ast")


def r004_none_sentinel(source: str, f: Finding) -> str:
    tree = ast.parse(source)
    func = _function(tree, f.symbol)
    param = f.extra.get("param")
    if func is None or not param:
        raise NoFix("function not found")
    args = func.args
    positional = args.posonlyargs + args.args
    pairs = list(zip(positional[len(positional) - len(args.defaults):], args.defaults))
    pairs += [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is not None]
    default = next((d for a, d in pairs if a.arg == param), None)
    if default is None:
        raise NoFix("default not found")
    empty = {"List": "[]", "Dict": "{}", "Set": "set()"}.get(type(default).__name__, ast.unparse(default))
    first = _first_body_line(func)
    ind = indent_of(source, first)
    # insert first (lower in the file), then replace the default (higher in the file)
    new = insert_lines(source, first, f"{ind}if {param} is None:\n{ind}    {param} = {empty}\n")
    return replace_node(new, default, "None")


def r005_arg_list(source: str, f: Finding) -> str:
    tree = ast.parse(source)
    call = _node_at(tree, f.line, ast.Call, lambda n: any(k.arg == "shell" for k in n.keywords))
    if not call.args:
        raise NoFix("no command argument")
    cmd = call.args[0]
    parts: list[ast.expr] = []

    def flatten(n):
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            flatten(n.left)
            flatten(n.right)
        else:
            parts.append(n)

    flatten(cmd)
    items: list[str] = []
    for p in parts:
        if isinstance(p, ast.Constant) and isinstance(p.value, str):
            if any(ch in p.value for ch in "|&;<>$`*?\"'"):
                raise NoFix("command uses shell syntax; review manually")
            items += [repr(tok) for tok in p.value.split()]
        elif isinstance(p, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)):
            items.append(ast.unparse(p))
        else:
            raise NoFix("command is not a simple concatenation")
    keywords = [k for k in call.keywords if k.arg != "shell"]
    new_call = ast.Call(func=call.func, args=[ast.List(elts=[ast.parse(i, mode="eval").body for i in items], ctx=ast.Load())]
                        + call.args[1:], keywords=keywords)
    return replace_node(source, call, ast.unparse(new_call))


def r006_env(source: str, f: Finding) -> str:
    tree = ast.parse(source)
    assign = _node_at(tree, f.line, ast.Assign)
    name = f.extra.get("name")
    new = replace_node(source, assign.value, f'os.environ.get("{name}", "")')
    return ensure_import(new, "os")


def r007_params(source: str, f: Finding) -> str:
    tree = ast.parse(source)
    call = _node_at(tree, f.line, ast.Call,
                    lambda n: isinstance(n.func, ast.Attribute) and n.func.attr in ("execute", "executemany"))
    q = call.args[0]
    if not isinstance(q, ast.JoinedStr) or len(call.args) != 1:
        raise NoFix("only f-string queries without existing parameters are rewritten automatically")
    values = q.values
    params: list[str] = []
    sql = ""
    for i, v in enumerate(values):
        if isinstance(v, ast.Constant):
            text = v.value
            # a placeholder written as '{x}' must lose its SQL quotes: '{x}' -> ?
            prev_is_ph = i > 0 and isinstance(values[i - 1], ast.FormattedValue)
            next_is_ph = i + 1 < len(values) and isinstance(values[i + 1], ast.FormattedValue)
            if prev_is_ph and text[:1] in ("'", '"'):
                text = text[1:]
            if next_is_ph and text[-1:] in ("'", '"'):
                text = text[:-1]
            sql += text
        else:
            if v.format_spec is not None or v.conversion != -1:
                raise NoFix("formatted placeholder; review manually")
            params.append(ast.unparse(v.value))
            sql += "?"
    param_src = ", ".join(params) + ("," if len(params) == 1 else "")
    return replace_node(source, q, f"{_quote(sql)}, ({param_src})")


def _quote(text: str) -> str:
    if '"' in text or "\\" in text:
        return repr(text)
    return f'"{text}"'


def r009_is_none(source: str, f: Finding) -> str:
    tree = ast.parse(source)
    cmp = _node_at(tree, f.line, ast.Compare,
                   lambda n: any(isinstance(o, (ast.Eq, ast.NotEq)) for o in n.ops))
    operands = [cmp.left] + list(cmp.comparators)
    new_ops = []
    for i, op in enumerate(cmp.ops):
        is_none = any(isinstance(x, ast.Constant) and x.value is None for x in (operands[i], operands[i + 1]))
        if is_none and isinstance(op, ast.Eq):
            new_ops.append(ast.Is())
        elif is_none and isinstance(op, ast.NotEq):
            new_ops.append(ast.IsNot())
        else:
            new_ops.append(op)
    new_cmp = ast.Compare(left=cmp.left, ops=new_ops, comparators=cmp.comparators)
    return replace_node(source, cmp, ast.unparse(new_cmp))


STRATEGIES: dict[str, list[Strategy]] = {
    "R001": [
        Strategy("Return a safe default", "Guard the denominator and return 0.0 for empty/zero input "
                 "(least disruptive: callers keep getting a float).", r001_default,
                 ("returned", "0.0", "== 0")),
        Strategy("Raise ValueError", "Guard the denominator and raise a clear ValueError for empty/zero input.",
                 r001_raise, ("valueerror", "did not raise", "raises")),
    ],
    "R002": [Strategy("Catch expected exceptions only",
                      "Replace the catch-all with `except (OSError, ValueError):` and keep the fallback.", r002_narrow)],
    "R003": [Strategy("Use ast.literal_eval", "Replace `eval` with `ast.literal_eval` (literals only).",
                      r003_literal_eval)],
    "R004": [Strategy("None sentinel", "Default to None and create a fresh object inside the function.",
                      r004_none_sentinel)],
    "R005": [Strategy("Argument list without shell", "Pass the command as a list and drop `shell=True`.",
                      r005_arg_list)],
    "R006": [Strategy("Read from environment", "Replace the literal with `os.environ.get(...)`.", r006_env)],
    "R007": [Strategy("Parameterised query", "Use `?` placeholders and pass values as a tuple.", r007_params)],
    "R009": [Strategy("Use `is None`", "Replace `== None` / `!= None` with `is None` / `is not None`.",
                      r009_is_none)],
    # R000, R008, PF01: no automatic fix (manual remediation is explained instead)
}
