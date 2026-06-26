#!/usr/bin/env python3
"""Hugging Face Space app for RentMasseur autonomous optimization.

Provides a web UI + API endpoints to:
- Trigger rotations manually
- View RL state and performance
- Run the orchestrator on schedule
- View generated content
- Track 24/7 availability status
"""

import os
import json
import glob
import subprocess
import time
from datetime import datetime, timezone
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="RentMasseur Autonomous Optimizer", docs_url="/docs")

CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")
ORCHESTRATOR_LOG = os.path.join(CONTENT_DIR, "orchestrator.log")

os.makedirs(CONTENT_DIR, exist_ok=True)


def load_json(path: str, default=None):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return default if default is not None else {}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    rl_state = load_json(os.path.join(CONTENT_DIR, "rl_state.json"), {})
    counts = {}
    for subdir in ["bios", "blog_posts", "interview_questions", "social_posts", "email_templates", "seo_keywords"]:
        path = os.path.join(CONTENT_DIR, subdir)
        counts[subdir] = len(glob.glob(os.path.join(path, "*"))) if os.path.exists(path) else 0

    availability = load_json(os.path.join(os.path.dirname(__file__), "availability.json"), {})

    html = f"""<!DOCTYPE html>
<html>
<head>
<title>RentMasseur Autonomous Optimizer</title>
<style>
body {{ font-family: -apple-system, sans-serif; margin: 0; padding: 20px; background: #0d1117; color: #c9d1d9; }}
h1 {{ color: #58a6ff; }}
.card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin: 10px 0; }}
.btn {{ display: inline-block; background: #238636; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; margin: 4px; }}
.btn.orange {{ background: #f0883e; }}
.btn.blue {{ background: #1f6feb; }}
pre {{ background: #0d1117; padding: 10px; border-radius: 6px; overflow-x: auto; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }}
.stat {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px; text-align: center; }}
.stat .num {{ font-size: 28px; font-weight: bold; color: #58a6ff; }}
.stat .label {{ font-size: 12px; color: #8b949e; }}
</style>
</head>
<body>
<h1>RentMasseur Autonomous Optimizer</h1>
<div class="card">
  <a class="btn" href="/run/orchestrator?all=1">Run Full Orchestrator</a>
  <a class="btn orange" href="/run/availability">Run Availability Keeper</a>
  <a class="btn blue" href="/run/stats">Collect Stats</a>
  <a class="btn" href="/api/report">JSON Report</a>
</div>
<div class="grid">
  <div class="stat"><div class="num">{counts.get('bios', 0)}</div><div class="label">Bios</div></div>
  <div class="stat"><div class="num">{counts.get('blog_posts', 0)}</div><div class="label">Blogs</div></div>
  <div class="stat"><div class="num">{counts.get('interview_questions', 0)}</div><div class="label">Interviews</div></div>
  <div class="stat"><div class="num">{counts.get('social_posts', 0)}</div><div class="label">Social</div></div>
  <div class="stat"><div class="num">{counts.get('email_templates', 0)}</div><div class="label">Emails</div></div>
  <div class="stat"><div class="num">{counts.get('seo_keywords', 0)}</div><div class="label">SEO</div></div>
</div>
<div class="card">
  <h2>RL State</h2>
  <pre>{json.dumps(rl_state, indent=2, default=str)[:2000]}</pre>
</div>
<div class="card">
  <h2>Availability</h2>
  <pre>{json.dumps(availability, indent=2, default=str)[:2000]}</pre>
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


@app.get("/api/report")
async def api_report():
    rl_state = load_json(os.path.join(CONTENT_DIR, "rl_state.json"), {})
    counts = {}
    for subdir in ["bios", "blog_posts", "interview_questions", "social_posts", "email_templates", "seo_keywords"]:
        path = os.path.join(CONTENT_DIR, subdir)
        counts[subdir] = len(glob.glob(os.path.join(path, "*"))) if os.path.exists(path) else 0
    availability = load_json(os.path.join(os.path.dirname(__file__), "availability.json"), {})
    return JSONResponse({
        "rl_state": rl_state,
        "content_counts": counts,
        "availability": availability,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


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
