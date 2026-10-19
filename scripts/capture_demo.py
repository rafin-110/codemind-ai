"""Drive the real Streamlit app in a real browser and save Phase 3 evidence.

Starts `streamlit run app.py` on a free port, walks the demo path with Playwright,
writes screenshots to docs/screenshots/phase3/ and the downloaded reports plus a
step log to docs/test-evidence/. Every assertion below must pass or the script exits 1.

Needs the dev-only extra:  pip install playwright   (uses the installed Chrome/Edge;
falls back to Playwright's bundled Chromium if neither is found).

    python scripts/capture_demo.py
"""

from __future__ import annotations

import io
import json
import socket
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from codemind.ingestion.zip_loader import zip_directory  # noqa: E402

SHOTS = ROOT / "docs" / "screenshots" / "phase3"
EVIDENCE = ROOT / "docs" / "test-evidence"
TIMEOUT = 60_000
expect.set_options(timeout=TIMEOUT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
log: list[str] = []


def step(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    log.append(line)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_idle(page: Page) -> None:
    """Wait until Streamlit finished the current script run."""
    page.wait_for_timeout(400)
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\"stStatusWidget\"]')"
        " || !document.querySelector('[data-testid=\"stStatusWidget\"]').innerText.includes('Running')",
        timeout=TIMEOUT)
    page.wait_for_timeout(600)


def nav(page: Page, label: str) -> None:
    page.locator('[data-testid="stSidebar"]').get_by_text(label, exact=True).click()
    wait_idle(page)


def shot(page: Page, name: str, scroll_to: str | None = None) -> None:
    if scroll_to:
        page.get_by_text(scroll_to).first.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
    page.screenshot(path=str(SHOTS / f"{name}.png"))
    step(f"screenshot {name}.png")


def click(page: Page, name: str) -> None:
    page.get_by_role("button", name=name).click()
    wait_idle(page)


def pick_finding(page: Page, fid: str) -> None:
    box = page.get_by_role("combobox", name="Finding details")
    box.click()
    page.get_by_role("option").filter(has_text=fid).first.click()
    wait_idle(page)


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    port = free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true",
         "--server.port", str(port), "--browser.gatherUsageStats", "false"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        with sync_playwright() as pw:
            browser = None
            for channel in ("chrome", "msedge", None):
                try:
                    browser = pw.chromium.launch(channel=channel) if channel else pw.chromium.launch()
                    step(f"browser: {channel or 'bundled chromium'} {browser.version}")
                    break
                except Exception:  # noqa: BLE001 - try the next browser
                    continue
            if browser is None:
                raise RuntimeError("no Chromium-based browser available")
            page = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True).new_page()
            page.set_default_timeout(TIMEOUT)
            for _ in range(60):
                try:
                    page.goto(url)
                    break
                except Exception:  # noqa: BLE001 - server still starting
                    time.sleep(1)
            expect(page.locator("h1").filter(has_text="CodeMind AI")).to_be_visible()
            wait_idle(page)
            step(f"app loaded at {url}")
            shot(page, "01_overview_empty")

            # 1. load + analyse the sample
            nav(page, "2. Upload & Explorer")
            click(page, "Load sample repository")
            expect(page.get_by_text("Repository: student_grades_app.zip").first).to_be_visible()
            shot(page, "02_upload_sample_loaded")
            click(page, "Run analysis (all agents)")
            expect(page.get_by_text("Analysis finished: 9 findings").first).to_be_visible()
            step("analysis finished: 9 findings")
            shot(page, "03_upload_analyzed", scroll_to="Technologies detected")

            nav(page, "1. Overview")
            shot(page, "04_overview_after_analysis")
            nav(page, "3. Agent Workflow")
            shot(page, "05_agent_workflow")

            # 2. findings: F-004 must be Confirmed by the baseline run
            nav(page, "4. Findings & Explainability")
            row = page.locator('[data-testid="stDataFrame"], table').first
            expect(row).to_be_visible()
            pick_finding(page, "F-004")
            expect(page.get_by_text("Confirmed").first).to_be_visible()
            step("F-004 shown as Confirmed (baseline test failure linked)")
            shot(page, "06_findings_F004_confirmed", scroll_to="Why it is a problem")

            nav(page, "5. Architecture Advisor")
            shot(page, "07_architecture_advisor")

            # 3. F-001: propose, then reject
            nav(page, "4. Findings & Explainability")
            pick_finding(page, "F-001")
            click(page, "Ask the Code Improvement Agent for a fix")
            expect(page.get_by_text("Proposal ready for F-001").first).to_be_visible()
            shot(page, "08_proposal_F001")
            click(page, "✖ Reject")
            expect(page.get_by_text("The original is unchanged and no working copy was made").first).to_be_visible()
            step("F-001 proposal rejected; no working copy made")
            shot(page, "09_F001_rejected")

            # 4. F-004: strategy 1 fails a real test, strategy 2 passes
            nav(page, "4. Findings & Explainability")
            pick_finding(page, "F-004")
            click(page, "Ask the Code Improvement Agent for a fix")
            expect(page.get_by_text("Return a safe default").first).to_be_visible()
            shot(page, "10_proposal_F004_attempt1")
            click(page, "✅ Approve and validate")
            expect(page.get_by_text("FAILED. The Code Improvement Agent proposed a different strategy").first).to_be_visible()
            step("attempt 1 failed validation (real pytest failure); retry proposed")
            shot(page, "11_F004_attempt2_after_failed_validation")
            click(page, "✅ Approve and validate")
            expect(page.get_by_text("Validation result: Passed").first).to_be_visible()
            expect(page.get_by_text("Original files re-hashed after validation: unchanged.").first).to_be_visible()
            step("attempt 2 validated: Passed, original unchanged")
            shot(page, "12_validation_passed")

            for label, ext in (("JSON report", "json"), ("Markdown report", "md")):
                with page.expect_download() as dl:
                    page.get_by_role("button", name=label).click()
                target = EVIDENCE / f"phase3_ui_report.{ext}"
                dl.value.save_as(target)
                step(f"downloaded {label} -> {target.relative_to(ROOT).as_posix()} ({target.stat().st_size} bytes)")
            report = json.loads((EVIDENCE / "phase3_ui_report.json").read_text(encoding="utf-8"))
            conf = {f["id"]: f["confidence"] for f in report["findings"]}
            assert len(conf) == 9 and conf["F-004"] == "Confirmed", conf
            assert [(v["patch_id"][:5], v["status"]) for v in report["validations"]] == [
                ("P-004", "Failed"), ("P-004", "Passed")], report["validations"]
            assert [a["decision"] for a in report["approvals"]] == ["rejected", "approved", "approved"]
            assert report["original_unchanged_at_report_time"] is True
            step("report checked: 9 findings, F-004 Confirmed, validations Failed->Passed, "
                 "decisions rejected/approved/approved, original unchanged")

            nav(page, "3. Agent Workflow")
            shot(page, "13_agent_workflow_after")

            # 5. ZIP upload path (untrusted: tests are not run)
            nav(page, "2. Upload & Explorer")
            page.locator('input[type="file"]').set_input_files(
                files=[{"name": "student_grades_app.zip", "mimeType": "application/zip",
                        "buffer": zip_directory(ROOT / "samples" / "student_grades_app")}])
            wait_idle(page)
            click(page, "Ingest ZIP")
            expect(page.get_by_text("student_grades_app.zip ingested safely.").first).to_be_visible()
            click(page, "Run analysis (all agents)")
            expect(page.get_by_text("Analysis finished: 9 findings").first).to_be_visible()
            shot(page, "14_upload_untrusted_zip")
            nav(page, "7. Validation Results")
            assert page.get_by_text("Baseline: tests on the untouched original").count() == 0, \
                "baseline tests ran for an untrusted upload"
            step("uploaded ZIP (not trusted) analysed: 9 findings; no baseline test run for untrusted code")
            nav(page, "2. Upload & Explorer")

            # 6. malicious ZIP is refused before anything is written
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("ok.py", "print('hi')\n")
                zf.writestr("../../evil.py", "import os\n")
            page.locator('input[type="file"]').set_input_files(
                files=[{"name": "traversal.zip", "mimeType": "application/zip", "buffer": buf.getvalue()}])
            wait_idle(page)
            click(page, "Ingest ZIP")
            expect(page.get_by_text("traversal", exact=False).first).to_be_visible()
            err = page.locator('[data-testid="stAlert"]').first.inner_text()
            step(f"path-traversal ZIP refused: {err.strip()[:160]}")
            shot(page, "15_upload_traversal_refused")
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    (EVIDENCE / "phase3_browser_e2e_log.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    step("ALL BROWSER E2E STEPS PASSED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - record the failure, never hide it
        step(f"FAILED: {type(exc).__name__}: {exc}")
        (EVIDENCE / "phase3_browser_e2e_log.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
        sys.exit(1)
