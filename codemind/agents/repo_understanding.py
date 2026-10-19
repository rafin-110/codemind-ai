"""Agent 1: Repository Understanding. Reads README, metadata and Python structure."""

from __future__ import annotations

from codemind.agents.base import Agent, AgentOutput
from codemind.analysis import code_index, metadata, readme_parser
from codemind.analysis.evidence import make_evidence
from codemind.models import RepoSnapshot, RepoSummary, WorkflowContext
from codemind.workspace import safe_join


def read_text(snapshot: RepoSnapshot, rel_path: str) -> str:
    return safe_join(snapshot.root, rel_path).read_text(encoding="utf-8", errors="replace")


def parse_all_python(snapshot: RepoSnapshot) -> list[code_index.ParsedModule]:
    return [code_index.parse_module(f.rel_path, read_text(snapshot, f.rel_path)) for f in snapshot.python_files]


class RepositoryUnderstandingAgent(Agent):
    name = "Repository Understanding Agent"
    role = "Explains purpose, structure, entry points and dependencies with evidence."

    def run(self, ctx: WorkflowContext, **_) -> AgentOutput:
        snap = ctx.snapshot
        assert snap is not None, "snapshot required"
        paths = [f.rel_path for f in snap.included_files]
        evidence, gaps = [], []

        # README -----------------------------------------------------------
        readme_path = readme_parser.find_readme(paths)
        readme = None
        if readme_path:
            text = read_text(snap, readme_path)
            readme = readme_parser.parse_readme(readme_path, text)
            if readme.title_line:
                evidence.append(make_evidence(readme_path, text, readme.title_line, note="README title", context=0))
            if readme.purpose_line:
                evidence.append(make_evidence(readme_path, text, readme.purpose_line, note="README purpose", context=0))
            if not readme.has_install:
                gaps.append(f"{readme_path}: no installation/setup section")
            if not readme.has_usage:
                gaps.append(f"{readme_path}: no usage/run section")
        else:
            gaps.append("No README found: purpose of the project is undocumented")

        # dependencies -----------------------------------------------------
        deps: list[str] = []
        for p in paths:
            name = p.split("/")[-1]
            if name == "requirements.txt" and p.count("/") == 0:
                text = read_text(snap, p)
                parsed = metadata.parse_requirements(text)
                deps += [n for n, _ in parsed]
                for n, line in parsed:
                    evidence.append(make_evidence(p, text, line, note=f"dependency '{n}'", context=0))
            elif name == "pyproject.toml" and p.count("/") == 0:
                deps += metadata.parse_pyproject(read_text(snap, p))
        if snap.python_files and not deps:
            gaps.append("No requirements.txt or pyproject.toml dependencies declared")

        # python structure -------------------------------------------------
        parsed = parse_all_python(snap)
        modules = [m.info for m in parsed if m.info]
        entry_points = []
        for m in parsed:
            if m.main_guard_line:
                entry_points.append(m.path)
                evidence.append(make_evidence(m.path, m.source, m.main_guard_line,
                                              note="entry point (__main__ guard)", context=1))
            if m.error:
                gaps.append(f"{m.path}: cannot be parsed ({m.error.msg}, line {m.error.lineno})")
            elif m.info and not m.info.docstring and not m.info.is_test and m.path.split("/")[-1] != "__init__.py":
                gaps.append(f"{m.path}: no module docstring")
            for fname, line in m.undocumented_functions:
                if m.info and not m.info.is_test:
                    gaps.append(f"{m.path}:{line} public function '{fname}' has no docstring")

        imports = {i for m in modules for i in m.imports}
        languages = {f.language for f in snap.included_files}
        tech = metadata.detect_technologies(languages, deps, imports)
        has_tests = any(m.is_test for m in modules)
        if snap.python_files and not has_tests:
            gaps.append("No automated tests found: fixes can only be checked statically")

        purpose = (readme.purpose if readme and readme.purpose else
                   "Not stated (no README purpose paragraph found).")
        ctx.summary = RepoSummary(
            title=(readme.title if readme and readme.title else snap.display_name),
            purpose=purpose,
            technologies=tech,
            entry_points=entry_points,
            modules=modules,
            dependencies=sorted(set(deps)),
            import_graph=code_index.internal_import_graph(parsed),
            doc_gaps=gaps,
            evidence=evidence,
            readme_sections=(readme.sections if readme else []),
            has_tests=has_tests,
        )
        return AgentOutput(
            f"Indexed {len(snap.included_files)} files ({len(snap.python_files)} Python), "
            f"{len(entry_points)} entry point(s), {len(tech)} technologies, {len(gaps)} documentation gaps.",
            [f"technologies: {', '.join(tech) or 'none'}", f"entry points: {', '.join(entry_points) or 'none'}"],
        )
