"""Index Python modules with `ast` (functions, classes, imports, entry points). No code runs."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from codemind.models import ModuleInfo


@dataclass
class ParsedModule:
    path: str
    source: str
    tree: ast.Module | None
    error: SyntaxError | None = None
    info: ModuleInfo | None = None
    main_guard_line: int = 0
    undocumented_functions: list[tuple[str, int]] = field(default_factory=list)


def _is_main_guard(node: ast.stmt) -> bool:
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    t = node.test
    names = [t.left] + list(t.comparators)
    has_name = any(isinstance(n, ast.Name) and n.id == "__name__" for n in names)
    has_main = any(isinstance(n, ast.Constant) and n.value == "__main__" for n in names)
    return has_name and has_main


def module_name(path: str) -> str:
    p = path[:-3] if path.endswith(".py") else path
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    return p.replace("/", ".")


def parse_module(path: str, source: str) -> ParsedModule:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return ParsedModule(path, source, None, exc)

    functions, classes, imports = [], [], []
    undocumented = []
    main_line = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            if not node.name.startswith("_") and ast.get_docstring(node) is None:
                undocumented.append((node.name, node.lineno))
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif _is_main_guard(node):
            main_line = node.lineno
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.append(node.module)

    name = path.split("/")[-1]
    is_test = name.startswith("test_") or name.endswith("_test.py") or "/tests/" in f"/{path}" or name == "conftest.py"
    doc = (ast.get_docstring(tree) or "").strip().splitlines()
    first_doc = doc[0] if doc else ""
    if is_test:
        role = f"Test module ({sum(f.startswith('test') for f in functions)} test functions)"
    elif main_line:
        role = "Entry point" + (f": {first_doc}" if first_doc else "")
    elif first_doc:
        role = first_doc
    elif functions or classes:
        role = f"Module defining {len(functions)} function(s) and {len(classes)} class(es); no docstring"
    else:
        role = "Package marker / constants" if name == "__init__.py" else "Module (no top-level definitions)"

    info = ModuleInfo(path=path, role=role, functions=tuple(functions), classes=tuple(classes),
                      imports=tuple(dict.fromkeys(imports)), is_entry_point=bool(main_line),
                      is_test=is_test, docstring=first_doc)
    return ParsedModule(path, source, tree, None, info, main_line, undocumented)


def internal_import_graph(modules: list[ParsedModule]) -> dict[str, list[str]]:
    by_name = {module_name(m.path): m.path for m in modules}
    graph: dict[str, list[str]] = {}
    for m in modules:
        if not m.info:
            continue
        targets = []
        for imp in m.info.imports:
            parts = imp.split(".")
            for k in range(len(parts), 0, -1):
                cand = ".".join(parts[:k])
                if cand in by_name and by_name[cand] != m.path:
                    targets.append(by_name[cand])
                    break
        graph[m.path] = sorted(set(targets))
    return graph
