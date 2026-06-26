#!/usr/bin/env python3
"""RentMasseur Operating System — Hugging Face Space App.

Glassmorphism UI + real-time metrics + competitor intelligence + RL/GA training.
Feeds into CI/CD pipelines to select perfect selling bio candidates.

Endpoints:
  GET /          — glassmorphism dashboard
  GET /api/os/report     — full operating system state
  POST /api/os/train     — train RL/GA on all bios
  GET /api/os/competitors — competitor intelligence
  GET /api/os/bios       — all bio candidates with scores
  POST /api/os/ingest    — ingest metrics from Vercel functions
  GET /run/orchestrator  — run master orchestrator
  GET /run/availability  — run availability keeper
  GET /run/ga-rl         — run GA+RL optimizer
"""

import os
import json
import glob
import subprocess
import time
import random
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv()

app = FastAPI(title="RentMasseur OS", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")
ORCHESTRATOR_LOG = os.path.join(CONTENT_DIR, "orchestrator.log")
VERCEL_BACKEND_URL = os.getenv("VERCEL_BACKEND_URL", "")
REBRANDLY_LINK = os.getenv("REBRANDLY_LINK", "")

os.makedirs(CONTENT_DIR, exist_ok=True)


def load_json(path: str, default=None):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return default if default is not None else {}


def _content_counts():
    counts = {}
    for subdir in ["bios", "blog_posts", "interview_questions", "social_posts", "email_templates", "seo_keywords", "ab_tests", "photos"]:
        path = os.path.join(CONTENT_DIR, subdir)
        counts[subdir] = len(glob.glob(os.path.join(path, "*"))) if os.path.exists(path) else 0
    return counts


def _load_all_bios():
    bios = []
    bios_dir = os.path.join(CONTENT_DIR, "bios")
    if os.path.exists(bios_dir):
        for f in sorted(glob.glob(os.path.join(bios_dir, "*.md")), reverse=True):
            with open(f, "r", encoding="utf-8") as fh:
                bios.append({
                    "id": os.path.basename(f).replace(".md", ""),
                    "file": os.path.basename(f),
                    "chars": os.path.getsize(f),
                    "preview": fh.read()[:200],
                })
    return bios


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    rl_state = load_json(os.path.join(CONTENT_DIR, "rl_state.json"), {})
    ga_state = load_json(os.path.join(CONTENT_DIR, "ga_rl_state.json"), {})
    counts = _content_counts()
    availability = load_json(os.path.join(os.path.dirname(__file__), "availability.json"), {})
    competitors = load_json(os.path.join(CONTENT_DIR, "competitor_bios.json"), [])
    revenue = ga_state.get("best_revenue", 0)
    target = 300
    progress = min(100, round((revenue / target) * 100, 1))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RentMasseur Operating System</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    font-family: 'Inter', sans-serif;
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    color: #fff;
    min-height: 100vh;
}}
.glass {{
    background: rgba(255, 255, 255, 0.08);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 20px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}}
.header {{
    padding: 30px 40px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
}}
.header h1 {{
    margin: 0;
    font-size: 32px;
    font-weight: 700;
    background: linear-gradient(90deg, #00f5ff, #b026ff, #ff2a6d);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}}
.sub {{ font-size: 14px; color: rgba(255,255,255,0.6); margin-top: 4px; }}
.live {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: #00f5a0;
    font-weight: 600;
}}
.pulse {{
    width: 10px;
    height: 10px;
    background: #00f5a0;
    border-radius: 50%;
    animation: pulse 2s infinite;
}}
@keyframes pulse {{
    0%, 100% {{ opacity: 1; transform: scale(1); }}
    50% {{ opacity: 0.5; transform: scale(1.3); }}
}}
.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 20px;
    padding: 0 40px 40px;
}}
.card {{
    padding: 24px;
    transition: transform 0.2s;
}}
.card:hover {{ transform: translateY(-4px); }}
.card h3 {{
    margin: 0 0 12px 0;
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: rgba(255,255,255,0.7);
}}
.card .num {{
    font-size: 42px;
    font-weight: 700;
    margin: 8px 0;
    background: linear-gradient(90deg, #00f5ff, #b026ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}}
.card .sub {{
    font-size: 13px;
    color: rgba(255,255,255,0.6);
}}
.progress-bar {{
    width: 100%;
    height: 12px;
    background: rgba(255,255,255,0.1);
    border-radius: 6px;
    overflow: hidden;
    margin-top: 12px;
}}
.progress-fill {{
    height: 100%;
    background: linear-gradient(90deg, #00f5ff, #b026ff);
    border-radius: 6px;
    transition: width 0.5s;
    width: {progress}%;
}}
.actions {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    padding: 0 40px 40px;
}}
.btn {{
    padding: 12px 24px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.25);
    background: rgba(255,255,255,0.1);
    color: #fff;
    text-decoration: none;
    font-weight: 600;
    font-size: 13px;
    transition: all 0.2s;
    cursor: pointer;
}}
.btn:hover {{
    background: rgba(255,255,255,0.2);
    border-color: rgba(255,255,255,0.4);
}}
.btn.primary {{
    background: linear-gradient(90deg, #00f5ff, #b026ff);
    border: none;
    color: #0f0c29;
}}
.btn.primary:hover {{ opacity: 0.9; }}
.section {{
    padding: 0 40px 40px;
}}
.section h2 {{
    font-size: 18px;
    margin-bottom: 16px;
    color: rgba(255,255,255,0.9);
}}
.table {{
    width: 100%;
    border-collapse: collapse;
}}
.table th, .table td {{
    text-align: left;
    padding: 12px;
    font-size: 13px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
}}
.table th {{
    color: rgba(255,255,255,0.6);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-size: 11px;
}}
pre {{
    background: rgba(0,0,0,0.3);
    padding: 16px;
    border-radius: 12px;
    overflow-x: auto;
    font-size: 12px;
    color: rgba(255,255,255,0.8);
}}
.link {{
    color: #00f5ff;
    text-decoration: none;
}}
.footer {{
    text-align: center;
    padding: 40px;
    font-size: 12px;
    color: rgba(255,255,255,0.4);
}}
</style>
</head>
<body>
<div class="header">
    <div>
        <h1>RentMasseur Operating System</h1>
        <div class="sub">Autonomous availability, dynamic content, revenue optimization</div>
    </div>
    <div class="live">
        <div class="pulse"></div>
        <span>LIVE SYSTEM</span>
    </div>
</div>

<div class="grid">
    <div class="card glass">
        <h3>Revenue Estimate</h3>
        <div class="num">${revenue:.0f}</div>
        <div class="sub">of $300/day target</div>
        <div class="progress-bar"><div class="progress-fill"></div></div>
    </div>
    <div class="card glass">
        <h3>24/7 Availability</h3>
        <div class="num">{availability.get('status', 'ACTIVE')}</div>
        <div class="sub">Last checked: {availability.get('checked_at', 'now')}</div>
    </div>
    <div class="card glass">
        <h3>Bio Candidates</h3>
        <div class="num">{counts.get('bios', 0)}</div>
        <div class="sub">Trained and scored</div>
    </div>
    <div class="card glass">
        <h3>GA Generations</h3>
        <div class="num">{ga_state.get('generation', 0)}</div>
        <div class="sub">Evolving toward $300/day</div>
    </div>
    <div class="card glass">
        <h3>Competitor Bios</h3>
        <div class="num">{len(competitors)}</div>
        <div class="sub">Analyzed for advantage</div>
    </div>
    <div class="card glass">
        <h3>Content Assets</h3>
        <div class="num">{sum(counts.values())}</div>
        <div class="sub">Total generated items</div>
    </div>
</div>

<div class="actions">
    <a href="/run/ga-rl?apply=1" class="btn primary">Train GA+RL & Apply Winner</a>
    <a href="/run/orchestrator?all=1" class="btn">Run Full Orchestrator</a>
    <a href="/run/availability" class="btn">Run Availability Keeper</a>
    <a href="/api/os/train" class="btn">Train on All Bios</a>
    <a href="/api/os/report" class="btn">Full OS Report</a>
    <a href="/api/os/competitors" class="btn">Competitor Intel</a>
</div>

<div class="section">
    <h2>Top Bio Candidates</h2>
    <div class="glass" style="padding: 20px;">
        <table class="table">
            <tr><th>ID</th><th>Chars</th><th>Preview</th></tr>
            {''.join([f"<tr><td>{b['id']}</td><td>{b['chars']}</td><td>{b['preview'][:80]}...</td></tr>" for b in _load_all_bios()[:5]]) or '<tr><td colspan="3">No bios yet</td></tr>'}
        </table>
    </div>
</div>

<div class="section">
    <h2>RL State</h2>
    <div class="glass" style="padding: 20px;">
        <pre>{json.dumps(rl_state, indent=2, default=str)[:1500]}</pre>
    </div>
</div>

<div class="footer">
    RentMasseur OS · HF Space + Vercel + GitHub Actions · Continuous optimization
</div>
</body>
</html>"""
    return HTMLResponse(html)


@app.get("/run/orchestrator")
async def run_orchestrator(background_tasks: BackgroundTasks, all: int = 1, dry: int = 0):
    dry_run = bool(dry)
    def run():
        cmd = ["python3", "orchestrator.py"]
        if all:
            cmd.append("--all")
        if dry_run:
            cmd.append("--dry-run")
        subprocess.run(cmd, cwd=os.path.dirname(__file__), capture_output=True, timeout=1200)
    background_tasks.add_task(run)
    return JSONResponse({"status": "started", "command": f"orchestrator --all{' --dry-run' if dry_run else ''}", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.get("/run/availability")
async def run_availability(background_tasks: BackgroundTasks):
    def run():
        subprocess.run(["python3", "rentmasseur_availability.py", "--once", "--headless", "true"], cwd=os.path.dirname(__file__), capture_output=True, timeout=600)
    background_tasks.add_task(run)
    return JSONResponse({"status": "started", "command": "availability keeper", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.get("/run/stats")
async def run_stats(background_tasks: BackgroundTasks):
    def run():
        subprocess.run(["python3", "rl_feedback.py"], cwd=os.path.dirname(__file__), capture_output=True, timeout=300)
    background_tasks.add_task(run)
    return JSONResponse({"status": "started", "command": "rl_feedback", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.get("/run/ga-rl")
async def run_ga_rl(background_tasks: BackgroundTasks, apply: int = 0):
    def run():
        cmd = ["python3", "ga_rl_optimizer.py", "--population", "12", "--generations", "5", "--target", "300"]
        subprocess.run(cmd, cwd=os.path.dirname(__file__), capture_output=True, timeout=1200)
        if apply:
            subprocess.run(["python3", "ga_rl_optimizer.py", "--apply-winner"], cwd=os.path.dirname(__file__), capture_output=True, timeout=600)
    background_tasks.add_task(run)
    return JSONResponse({"status": "started", "command": "ga+rl optimizer", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.get("/api/os/report")
async def api_os_report():
    rl_state = load_json(os.path.join(CONTENT_DIR, "rl_state.json"), {})
    ga_state = load_json(os.path.join(CONTENT_DIR, "ga_rl_state.json"), {})
    counts = _content_counts()
    availability = load_json(os.path.join(os.path.dirname(__file__), "availability.json"), {})
    competitors = load_json(os.path.join(CONTENT_DIR, "competitor_bios.json"), [])
    return JSONResponse({
        "rl_state": rl_state,
        "ga_state": ga_state,
        "content_counts": counts,
        "availability": availability,
        "competitors_analyzed": len(competitors),
        "rebrandly_link": REBRANDLY_LINK,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/api/os/bios")
async def api_os_bios():
    return JSONResponse({"bios": _load_all_bios()})


@app.get("/api/os/competitors")
async def api_os_competitors():
    competitors = load_json(os.path.join(CONTENT_DIR, "competitor_bios.json"), [])
    return JSONResponse({"competitors": competitors[:50]})


@app.get("/api/os/train")
async def api_os_train(background_tasks: BackgroundTasks):
    def run():
        subprocess.run(["python3", "bio_ab_tester.py", "--competitors-only"], cwd=os.path.dirname(__file__), capture_output=True, timeout=600)
        subprocess.run(["python3", "content_generator.py", "--bios-only"], cwd=os.path.dirname(__file__), capture_output=True, timeout=900)
        subprocess.run(["python3", "ga_rl_optimizer.py", "--population", "12", "--generations", "5", "--target", "300"], cwd=os.path.dirname(__file__), capture_output=True, timeout=1200)
    background_tasks.add_task(run)
    return JSONResponse({"status": "training_started", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.post("/api/os/ingest")
async def api_os_ingest(request: Request):
    """Ingest metrics from Vercel functions or extension."""
    data = await request.json()
    os.makedirs(CONTENT_DIR, exist_ok=True)
    ingest_path = os.path.join(CONTENT_DIR, "metrics_ingest.jsonl")
    with open(ingest_path, "a") as f:
        f.write(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), **data}) + "\n")
    try:
        subprocess.run(["python3", "rl_feedback.py"], cwd=os.path.dirname(__file__), capture_output=True, timeout=300)
    except Exception:
        pass
    return JSONResponse({"status": "ingested", "records": 1})


@app.get("/api/rl/state")
async def api_rl_state():
    return JSONResponse(load_json(os.path.join(CONTENT_DIR, "rl_state.json"), {}))


@app.post("/api/rl/state")
async def api_rl_state_post(state: dict):
    with open(os.path.join(CONTENT_DIR, "rl_state.json"), "w") as f:
        json.dump(state, f)
    return JSONResponse({"status": "saved"})


@app.get("/api/content/{subdir}")
async def api_content(subdir: str):
    path = os.path.join(CONTENT_DIR, subdir)
    if not os.path.exists(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    files = sorted(glob.glob(os.path.join(path, "*")))
    return JSONResponse([{"file": os.path.basename(f), "size": os.path.getsize(f)} for f in files])


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "service": "rentmasseur-optimizer", "timestamp": datetime.now(timezone.utc).isoformat()})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
