"""T-LLM-01 and advisor behaviour."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from codemind.agents.bug_risk import BugRiskAgent
from codemind.agents.repo_understanding import RepositoryUnderstandingAgent
from codemind.agents.solution_advisor import SolutionAdvisorAgent
from codemind.analysis.advisor_kb import KB
from codemind.analysis.ast_rules import RULES
from codemind.ingestion.zip_loader import ingest_zip, zip_directory
from codemind.llm.mock_llm import MockLLM
from codemind.llm.ollama_llm import OllamaLLM
from codemind.models import WorkflowContext
from tests.helpers import SAMPLE


def test_every_rule_has_advice_with_alternatives():
    for rule_id in RULES:
        assert rule_id in KB and KB[rule_id]["alternatives"], rule_id


def test_advisor_on_sample(tmp_path):
    ctx = WorkflowContext(run_id="t", snapshot=ingest_zip(zip_directory(SAMPLE), tmp_path / "r"))
    RepositoryUnderstandingAgent().execute(ctx)
    BugRiskAgent().execute(ctx)
    SolutionAdvisorAgent(MockLLM()).execute(ctx)
    assert set(ctx.recommendations) == {f.id for f in ctx.findings}
    by_rule = {ctx.finding(fid).rule_id: r for fid, r in ctx.recommendations.items()}
    assert "average()" in by_rule["R001"].current_approach and "len(scores)" in by_rule["R001"].current_approach
    assert len(by_rule["R001"].alternatives) >= 2
    assert by_rule["R009"].keep_current is True          # explicit "existing approach is fine" case
    assert by_rule["R007"].recommended.startswith("Parameterised")
    assert all(r.text_origin == "deterministic" for r in ctx.recommendations.values())


def test_ollama_unreachable_falls_back():
    llm = OllamaLLM(url="http://127.0.0.1:9", timeout=1)
    assert llm.available() is False
    out = llm.rephrase("Original text.", "ctx")
    assert out.text == "Original text." and out.origin == "deterministic" and "unavailable" in out.note


def _fake_ollama(response_text):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            body = json.dumps({"response": response_text}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.mark.parametrize("reply,ok", [
    ("Dividing by zero crashes; check the list first.", True),
    ("```python\nimport os\n```", False),            # code is rejected
    ("", False),                                      # empty is rejected
    ("x" * 1000, False),                              # too long is rejected
])
def test_ollama_output_is_validated(reply, ok):
    srv = _fake_ollama(reply)
    try:
        out = OllamaLLM(url=f"http://127.0.0.1:{srv.server_port}", timeout=3).rephrase("Original.", "t")
    finally:
        srv.shutdown()
    if ok:
        assert out.text == reply and out.origin.startswith("llm:")
    else:
        assert out.text == "Original." and out.origin == "deterministic"
