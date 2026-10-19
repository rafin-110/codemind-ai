"""T-RULE-01..10, T-BND-01: each rule fires on positive cases and stays quiet on negative ones."""

import ast
import json
import re
import textwrap

import pytest

from codemind.agents.bug_risk import BugRiskAgent
from codemind.agents.repo_understanding import RepositoryUnderstandingAgent
from codemind.analysis.ast_rules import run_rules
from codemind.ingestion.zip_loader import ingest_zip, zip_directory
from codemind.models import Severity, WorkflowContext
from tests.helpers import ROOT, SAMPLE, make_zip


def rules_for(code: str) -> list[tuple[str, int]]:
    return [(h.rule_id, h.line) for h in run_rules(ast.parse(textwrap.dedent(code)))]


POSITIVE = {
    "R001": ("def avg(xs):\n    return sum(xs) / len(xs)\n", 2),
    "R002": ("try:\n    x = 1\nexcept:\n    pass\n", 3),
    "R003": ("def f():\n    s = input()\n    return eval(s)\n", 3),
    "R004": ("def f(a, items={}):\n    return items\n", 1),
    "R005": ("import subprocess\nsubprocess.run('ls ' + d, shell=True)\n", 2),
    "R006": ("DB_PASSWORD = 'correcthorse99'\n", 1),
    "R007": ("def q(c, n):\n    c.execute('SELECT * FROM t WHERE n = ' + n)\n", 2),
    "R008": ("n = int(input('n? '))\n", 1),
    "R009": ("if x != None:\n    pass\n", 1),
}

NEGATIVE = {
    "R001": "def avg(xs):\n    if not xs:\n        return 0\n    return sum(xs) / len(xs)\n",
    "R001b": "def half(x):\n    return x / 2\n",
    "R001c": "def f(a, b):\n    try:\n        return a / b\n    except ZeroDivisionError:\n        return 0\n",
    "R001d": "msg = 'hello %s' % name\n",
    "R002": "try:\n    x = 1\nexcept ValueError:\n    pass\n",
    "R003": "import ast\nv = ast.literal_eval(s)\n",
    "R004": "def f(a, items=None):\n    return items or []\n",
    "R005": "import subprocess\nsubprocess.run(['ls', d])\n",
    "R006": "PASSWORD_PROMPT = 'Enter your password please'\nTOKEN = ''\n",
    "R007": "def q(c, n):\n    c.execute('SELECT * FROM t WHERE n = ?', (n,))\n",
    "R008": "try:\n    n = int(input())\nexcept ValueError:\n    n = 0\n",
    "R009": "if x is None:\n    pass\n",
}


@pytest.mark.parametrize("rule", sorted(POSITIVE))
def test_rule_fires_on_positive_case(rule):
    code, line = POSITIVE[rule]
    assert (rule, line) in rules_for(code)


@pytest.mark.parametrize("case", sorted(NEGATIVE))
def test_rule_quiet_on_negative_case(case):
    rule = case[:4]
    assert all(r != rule for r, _ in rules_for(NEGATIVE[case]))


def test_eval_on_input_is_critical_but_dynamic_string_is_high():
    hits = run_rules(ast.parse("def f():\n    return eval(input())\ndef g(s):\n    return eval(s)\n"))
    sev = {h.line: h.severity for h in hits if h.rule_id == "R003"}
    assert sev[2] is Severity.CRITICAL and sev[4] is None   # None -> rule default (High)


def test_os_system_flagged():
    assert ("R005", 2) in rules_for("import os\nos.system('rm ' + p)\n")


def test_fstring_and_format_sql_flagged():
    assert ("R007", 1) in rules_for("c.execute(f'SELECT {x}')\n")
    assert ("R007", 1) in rules_for("c.execute('SELECT {}'.format(x))\n")
    assert rules_for("c.execute(f'SELECT 1')\n") == []   # f-string with no placeholders is static


def _analyse(data: bytes, tmp_path):
    ctx = WorkflowContext(run_id="t", snapshot=ingest_zip(data, tmp_path / "r"))
    RepositoryUnderstandingAgent().execute(ctx)
    BugRiskAgent().execute(ctx)
    return ctx


def test_sample_matches_ground_truth_exactly(tmp_path):
    """T-RULE-10: every planted issue at the exact file + line, and nothing else."""
    truth = json.loads((ROOT / "samples" / "EXPECTED_FINDINGS.json").read_text())
    ctx = _analyse(zip_directory(SAMPLE), tmp_path)
    found = {(f.rule_id, f.file, f.line) for f in ctx.findings if f.source == "ast-rule"}
    expected = {(e["rule_id"], e["file"], e["line"]) for e in truth["expected"]}
    assert found == expected
    assert not any(f.symbol == "percentage" for f in ctx.findings)


def test_findings_have_all_required_fields_and_ids(tmp_path):
    ctx = _analyse(zip_directory(SAMPLE), tmp_path)
    ids = [f.id for f in ctx.findings]
    assert ids == [f"F-{i:03d}" for i in range(1, len(ids) + 1)]
    for f in ctx.findings:
        assert f.title and f.category and f.severity and f.confidence
        assert f.file and f.line > 0
        assert re.search(rf"^>\s+{f.line} \|", f.evidence.snippet, re.M), f.evidence.snippet
        assert f.why_problematic and f.impact and f.remediation and f.validation_method
    ranks = [(-f.severity.rank, -f.confidence.rank) for f in ctx.findings]
    assert ranks == sorted(ranks)


def test_secret_never_in_evidence(tmp_path):
    ctx = _analyse(zip_directory(SAMPLE), tmp_path)
    blob = json.dumps([f.evidence.snippet for f in ctx.findings])
    assert "4f9a2b7c1d8e3f60" not in blob


def test_test_files_are_not_flagged(tmp_path):
    ctx = _analyse(make_zip({"tests/test_x.py": "def test_a():\n    assert eval('1') == 1\n"}), tmp_path)
    assert ctx.findings == []


@pytest.mark.parametrize("files,expected_rules", [
    ({"empty.py": ""}, set()),                                     # boundary: empty file
    ({"bad.py": "def broken(:\n    pass\n"}, {"R000"}),            # invalid: syntax error
    ({"nested.py": "def outer():\n    def inner(xs):\n        return 1 / len(xs)\n    return inner\n"}, {"R001"}),
    ({"README.md": "# only docs\n"}, set()),                       # no Python at all
])
def test_boundary_inputs(tmp_path, files, expected_rules):
    ctx = _analyse(make_zip(files), tmp_path)
    assert {f.rule_id for f in ctx.findings} == expected_rules


def test_syntax_error_finding_has_line(tmp_path):
    ctx = _analyse(make_zip({"bad.py": "x = 1\ny = (\n"}), tmp_path)
    f = ctx.findings[0]
    assert f.rule_id == "R000" and f.file == "bad.py" and f.line >= 2


def test_pyflakes_optional_undefined_name(tmp_path):
    pytest.importorskip("pyflakes")
    ctx = _analyse(make_zip({"m.py": "def f():\n    return undefined_thing\n"}), tmp_path)
    assert ("PF01", 2) in {(f.rule_id, f.line) for f in ctx.findings}
