# CodeMind AI — Demo Checklist

Use this before the 5-minute demo. The timed script is `presentation/DEMO_SCRIPT.md`.

## The day before

- [ ] `python -m venv .venv` → activate → `python -m pip install -r requirements.txt`
- [ ] `python -m pytest -q` shows **104 passed, 1 skipped** (or 105 passed if pyflakes is installed)
- [ ] `streamlit run app.py` opens http://localhost:8501 with no error
- [ ] Run the demo path once end to end (below). Takes about 2 minutes.
- [ ] Open `presentation/CodeMind_AI_CA3.pptx` on the presenting laptop; check fonts and images
- [ ] Charger, HDMI/USB-C adapter; laptop set to never sleep during the session

## Ten minutes before

- [ ] Close other apps; turn off notifications
- [ ] Start the app: `streamlit run app.py`; browser zoom 100–110 % so the sidebar and a full diff fit
- [ ] Sidebar shows workflow state **RECEIVED**. If not, refresh the tab (each tab is a fresh run)
- [ ] PPT open on slide 1, browser in a second window
- [ ] Backup: `docs/screenshots/phase3/` open in a folder, in case the app or laptop fails

## Demo path (what must happen)

| # | Click | You should see |
|---|---|---|
| 1 | 2. Upload & Explorer → **Load sample repository** | directory tree + README preview |
| 2 | **Run analysis (all agents)** | "Analysis finished: 9 findings" |
| 3 | 3. Agent Workflow | task plan with 5 steps done, decision log |
| 4 | 4. Findings → pick **F-004** | badges High · **Confirmed**, yellow box "Confirmed by the baseline test run … test_average_empty_raises" |
| 5 | 5. Architecture Advisor | current approach vs alternatives, trade-offs |
| 6 | Findings → **F-001** → *Ask the Code Improvement Agent for a fix* → **Reject** | "Rejected … original is unchanged and no working copy was made" |
| 7 | Findings → **F-004** → ask for a fix → **Approve and validate** | red banner: attempt 1 FAILED, agent proposes "Raise ValueError" |
| 8 | **Approve and validate** again | "Validation result: Passed", 9 passed / 0 failed, "Original files re-hashed after validation: unchanged" |
| 9 | 7. Validation Results → **Markdown report** | report downloads |
| 10 | 3. Agent Workflow | every state change with its reason |

## If something goes wrong

| Problem | Fix |
|---|---|
| Buttons greyed out / wrong state | Refresh the browser tab and start again from step 1 (about 30 s) |
| Port 8501 busy | `streamlit run app.py --server.port 8502` |
| `ModuleNotFoundError: streamlit` | venv not activated: `.venv\Scripts\activate` |
| Validation takes > 10 s | first pytest start on a cold laptop; wait, it has a 60 s timeout |
| App will not start at all | present from `docs/screenshots/phase3/01…15` in order; they are from a real run |
