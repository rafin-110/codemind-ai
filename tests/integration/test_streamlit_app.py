"""T-UI-01/02: the Streamlit app starts, every view renders, and the demo works through the UI."""

import ast
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from codemind import config
from tests.helpers import ROOT

PAGES = ["1. Overview", "2. Upload & Explorer", "3. Agent Workflow", "4. Findings & Explainability",
         "5. Architecture Advisor", "6. Proposed Changes", "7. Validation Results"]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_WORKSPACE", tmp_path / "ws")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    at.run()
    assert not at.exception
    return at


def goto(at, page):
    at.sidebar.radio(key="page").set_value(page).run()
    assert not at.exception, at.exception


def test_every_view_renders_before_and_after_analysis(app):
    for p in PAGES:
        goto(app, p)
    goto(app, "2. Upload & Explorer")
    app.button(key="load_sample").click().run()
    app.button(key="run_analysis").click().run()
    assert not app.exception
    for p in PAGES:
        goto(app, p)


def test_demo_through_ui(app):
    goto(app, "2. Upload & Explorer")
    app.button(key="load_sample").click().run()
    assert app.button(key="run_analysis").disabled is False
    app.button(key="run_analysis").click().run()
    assert app.button(key="run_analysis").disabled is True          # no duplicate analysis on rerun
    orch = app.session_state["orch"]
    assert len(orch.ctx.findings) == 9

    goto(app, "6. Proposed Changes")
    assert not any(b.key.startswith("approve_") for b in app.button)  # nothing to approve yet

    goto(app, "4. Findings & Explainability")
    r002 = next(f.id for f in orch.ctx.findings if f.rule_id == "R002")
    app.selectbox(key="finding_pick").set_value(r002).run()
    app.button(key=f"propose_{r002}").click().run()
    assert app.sidebar.radio(key="page").value == "6. Proposed Changes"
    p = orch.ctx.current_proposal
    app.button(key=f"reject_{p.patch_hash}").click().run()
    assert orch.ctx.state.value == "FINDINGS_READY"
    assert app.button(key=f"approve_{p.patch_hash}").disabled            # stale buttons are disabled

    goto(app, "4. Findings & Explainability")
    r001 = next(f.id for f in orch.ctx.findings if f.rule_id == "R001")
    app.selectbox(key="finding_pick").set_value(r001).run()
    app.button(key=f"propose_{r001}").click().run()
    first = orch.ctx.current_proposal
    app.button(key=f"approve_{first.patch_hash}").click().run()
    assert orch.ctx.state.value == "AWAITING_APPROVAL" and any("FAILED" in e.value for e in app.error)
    second = orch.ctx.current_proposal
    app.button(key=f"approve_{second.patch_hash}").click().run()
    assert orch.ctx.state.value == "VALIDATED"
    assert app.sidebar.radio(key="page").value == "7. Validation Results"
    assert [m.value for m in app.metric][:3] == ["9", "0", "0"]


def test_core_package_does_not_import_streamlit():
    for path in (ROOT / "codemind").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(n.split(".")[0] == "streamlit" for n in names), path


def test_failed_baseline_reason_is_visible_in_ui(app):
    """A baseline that produced no results must be explained, never shown as a bare '0 passed'."""
    from tests.helpers import make_zip
    orch = app.session_state["orch"]
    orch.load_zip(make_zip({"app.py": "def f():\n    return 1\n",
                            "tests/test_app.py": "from app import f\n\n\ndef test_f():\n    assert f() == 1\n",
                            "conftest.py": "raise RuntimeError('broken env')\n"}), "crash.zip", trusted=True)
    orch.analyze()
    for page in ("1. Overview", "7. Validation Results"):
        goto(app, page)
        assert any("produced no results" in w.value for w in app.warning), page
    assert orch.ctx.baseline.status.value == "Not run"
