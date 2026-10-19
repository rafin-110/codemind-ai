"""T-RDM-01/02: README, metadata, structure analysis."""

from codemind.agents.repo_understanding import RepositoryUnderstandingAgent
from codemind.analysis.readme_parser import parse_readme
from codemind.analysis.evidence import redact
from codemind.ingestion.zip_loader import ingest_zip, zip_directory
from codemind.models import WorkflowContext
from tests.helpers import SAMPLE, make_zip


def _run(snapshot):
    ctx = WorkflowContext(run_id="t", snapshot=snapshot)
    RepositoryUnderstandingAgent().execute(ctx)
    return ctx


def test_sample_summary(tmp_path):
    ctx = _run(ingest_zip(zip_directory(SAMPLE), tmp_path / "r"))
    s = ctx.summary
    assert s.title == "Student Grades App (synthetic sample)"
    assert "command-line tool" in s.purpose
    assert s.entry_points == ["main.py"]
    assert "pytest" in s.dependencies
    assert {"Python", "SQLite", "pytest"} <= set(s.technologies)
    assert s.has_tests
    assert "grades/stats.py" in s.import_graph["grades/cli.py"]
    assert any(e.file == "main.py" and e.note.startswith("entry point") for e in s.evidence)
    roles = {m.path: m.role for m in s.modules}
    assert roles["grades/stats.py"] == "Statistics helpers for student scores."
    assert roles["tests/test_stats.py"].startswith("Test module")
    assert ctx.log[-1].agent == "Repository Understanding Agent"


def test_repo_without_readme_records_gap(tmp_path):
    ctx = _run(ingest_zip(make_zip({"tool.py": "def f(x):\n    return x\n"}), tmp_path / "r"))
    gaps = " ".join(ctx.summary.doc_gaps)
    assert "No README" in gaps
    assert "No automated tests" in gaps
    assert "'f' has no docstring" in gaps


def test_unparseable_file_is_reported_not_crashing(tmp_path):
    ctx = _run(ingest_zip(make_zip({"README.md": "# X\n\nA thing.\n", "bad.py": "def (:\n"}), tmp_path / "r"))
    assert any("cannot be parsed" in g for g in ctx.summary.doc_gaps)


def test_readme_parser_sections_and_code_blocks():
    info = parse_readme("README.md", "# T\n\nIntro text here.\n\n## Install\n```\n# not a heading\n```\n## Usage\n")
    assert info.title == "T" and info.purpose == "Intro text here."
    assert info.sections == ["Install", "Usage"] and info.has_install and info.has_usage


def test_redaction():
    assert "4f9a2b7c" not in redact('API_KEY = "sk-demo-4f9a2b7c1d8e3f60"')
    assert "hunter2!" not in redact("password = 'hunter2!'")
    assert redact("x = 'short'") == "x = 'short'"
