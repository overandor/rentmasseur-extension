#!/usr/bin/env python3
"""Booking availability API server.

Serves the latest availability.json produced by checker.py. Also provides
widget.html and verify.html landing pages for the extension buttons.
"""

import json
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

APP_DIR = Path(__file__).resolve().parent
AVAILABILITY_FILE = APP_DIR / "availability.json"

app = FastAPI(title="RentMasseur Availability API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_availability():
    if not AVAILABILITY_FILE.exists():
        return {"generated_at": None, "mode": "none", "count": 0, "providers": []}
    with open(AVAILABILITY_FILE, "r") as f:
        return json.load(f)


@app.get("/api/availability")
def list_availability():
    return load_availability()


@app.get("/api/availability/{slug}")
def get_availability(slug: str):
    data = load_availability()
    for provider in data.get("providers", []):
        if provider.get("slug") == slug:
            return provider
    raise HTTPException(status_code=404, detail="Provider not found")


@app.post("/api/refresh")
def refresh(mock: bool = False):
    try:
        cmd = ["python3", str(APP_DIR / "checker.py"), "--output", str(AVAILABILITY_FILE)]
        if mock:
            cmd.append("--mock")
        subprocess.run(cmd, check=True, cwd=APP_DIR)
        return load_availability()
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Checker failed: {e}")


WIDGET_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Book Appointment</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a1f; color: #f0f0f5; margin: 0; padding: 40px; }
    .card { max-width: 480px; margin: 0 auto; background: #222; padding: 24px; border-radius: 12px; border: 1px solid #333; }
    h1 { margin-top: 0; font-size: 20px; }
    .meta { color: #9a9aa3; font-size: 14px; margin-bottom: 16px; }
    input, button { width: 100%; padding: 10px; margin-bottom: 10px; border-radius: 6px; border: 1px solid #444; background: #111; color: #f0f0f5; box-sizing: border-box; }
    button { background: #cc8b4a; border: none; font-weight: 600; cursor: pointer; }
    button:hover { background: #e09d5a; }
  </style>
</head>
<body>
  <div class="card">
    <h1 id="provider">Book Appointment</h1>
    <div class="meta" id="source"></div>
    <form>
      <input type="text" placeholder="Your name" required>
      <input type="email" placeholder="Your email" required>
      <input type="datetime-local" required>
      <button type="submit">Request Booking</button>
    </form>
    <p class="meta" id="status"></p>
  </div>
  <script>
    const params = new URLSearchParams(location.search);
    const provider = params.get('provider') || 'unknown';
    document.getElementById('provider').textContent = 'Book: ' + provider;
    document.getElementById('source').textContent = 'Source: ' + (params.get('source') || 'direct');
    document.querySelector('form').addEventListener('submit', e => {
      e.preventDefault();
      document.getElementById('status').textContent = 'Booking request submitted (demo).';
    });
  </script>
</body>
</html>
"""

VERIFY_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Verify Video Call</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a1f; color: #f0f0f5; margin: 0; padding: 40px; }
    .card { max-width: 480px; margin: 0 auto; background: #222; padding: 24px; border-radius: 12px; border: 1px solid #333; }
    h1 { margin-top: 0; font-size: 20px; }
    .meta { color: #9a9aa3; font-size: 14px; margin-bottom: 16px; }
    button { width: 100%; padding: 12px; background: #8b5cf6; border: none; border-radius: 8px; color: #fff; font-weight: 600; cursor: pointer; }
    button:hover { background: #a78bfa; }
  </style>
</head>
<body>
  <div class="card">
    <h1 id="provider">Verify Video Call</h1>
    <div class="meta" id="source"></div>
    <button id="start">Start Verification Call</button>
    <p class="meta" id="status"></p>
  </div>
  <script>
    const params = new URLSearchParams(location.search);
    const provider = params.get('provider') || 'unknown';
    document.getElementById('provider').textContent = 'Verify: ' + provider;
    document.getElementById('source').textContent = 'Source: ' + (params.get('source') || 'direct');
    document.getElementById('start').addEventListener('click', () => {
      document.getElementById('status').textContent = 'Demo: verification call would start here.';
    });
  </script>
</body>
</html>
"""


@app.get("/widget.html", response_class=HTMLResponse)
def widget():
    return WIDGET_HTML


@app.get("/verify.html", response_class=HTMLResponse)
def verify():
    return VERIFY_HTML


@app.get("/")
def root():
    return {"service": "RentMasseur Availability API", "endpoints": ["/api/availability", "/api/refresh"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=3000)
