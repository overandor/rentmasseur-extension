#!/usr/bin/env python3
"""Dashboard server — FastAPI app showing all content, availability, and stats.

Provides a web UI to browse generated bios, blog posts, interview questions,
social media posts, email templates, SEO keywords, and availability status.

Usage:
    python3 dashboard.py
    python3 dashboard.py --port 8080
"""

import argparse
import json
import os
import glob
import sys
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")
AVAILABILITY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "availability.json")

app = FastAPI(title="RentMasseur Dashboard", docs_url="/api/docs")


def _list_content(subdir: str, ext: str = "md") -> list:
    directory = os.path.join(CONTENT_DIR, subdir)
    if not os.path.exists(directory):
        return []
    files = sorted(glob.glob(os.path.join(directory, f"*.{ext}")), reverse=True)
    return [{"filename": os.path.basename(f), "path": f, "size": os.path.getsize(f)} for f in files]


def _read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    bios = _list_content("bios")
    blogs = _list_content("blog_posts")
    questions = _list_content("interview_questions")
    social = _list_content("social_posts")
    emails = _list_content("email_templates")
    seo = _list_content("seo_keywords", "json")
    analyses = _list_content("", "md")

    avail_data = {}
    if os.path.exists(AVAILABILITY_FILE):
        try:
            with open(AVAILABILITY_FILE, "r") as f:
                avail_data = json.load(f)
        except Exception:
            pass

    def render_list(title: str, items: list, subdir: str) -> str:
        if not items:
            return f"<h2>{title}</h2><p>No content yet.</p>"
        cards = "".join([
            f'<div class="card"><h3>{i["filename"]}</h3>'
            f'<p>{i["size"]} bytes</p>'
            f'<a href="/view/{subdir}/{i["filename"]}">View</a></div>'
            for i in items[:20]
        ])
        return f"<h2>{title} ({len(items)})</h2><div class='grid'>{cards}</div>"

    return f"""<!DOCTYPE html>
<html>
<head>
<title>RentMasseur Dashboard</title>
<style>
body {{ font-family: -apple-system, sans-serif; margin: 0; padding: 20px; background: #0d1117; color: #c9d1d9; }}
h1 {{ color: #58a6ff; }}
h2 {{ color: #79c0ff; margin-top: 30px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px; }}
.card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px; }}
.card h3 {{ font-size: 14px; color: #58a6ff; margin: 0 0 8px 0; word-break: break-all; }}
.card a {{ color: #58a6ff; text-decoration: none; font-size: 13px; }}
.stats {{ display: flex; gap: 20px; margin: 20px 0; }}
.stat {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px 24px; text-align: center; }}
.stat .num {{ font-size: 32px; font-weight: bold; color: #58a6ff; }}
.stat .label {{ font-size: 12px; color: #8b949e; }}
pre {{ background: #161b22; padding: 16px; border-radius: 8px; overflow-x: auto; white-space: pre-wrap; }}
</style>
</head>
<body>
<h1>RentMasseur Dashboard</h1>
<div class="stats">
<div class="stat"><div class="num">{len(bios)}</div><div class="label">Bios</div></div>
<div class="stat"><div class="num">{len(blogs)}</div><div class="label">Blog Posts</div></div>
<div class="stat"><div class="num">{len(questions)}</div><div class="label">Interview Qs</div></div>
<div class="stat"><div class="num">{len(social)}</div><div class="label">Social Posts</div></div>
<div class="stat"><div class="num">{len(emails)}</div><div class="label">Email Templates</div></div>
<div class="stat"><div class="num">{len(seo)}</div><div class="label">SEO Sets</div></div>
</div>
{render_list("Mass Analysis Reports", [a for a in analyses if "mass_analysis" in a["filename"]], "")}
{render_list("Bios", bios, "bios")}
{render_list("Blog Posts", blogs, "blog_posts")}
{render_list("Interview Questions", questions, "interview_questions")}
{render_list("Social Media Posts", social, "social_posts")}
{render_list("Email Templates", emails, "email_templates")}
{render_list("SEO Keywords", seo, "seo_keywords")}
<h2>Availability Data</h2>
<pre>{json.dumps(avail_data, indent=2)}</pre>
</body>
</html>"""


@app.get("/view/{subdir}/{filename}", response_class=HTMLResponse)
async def view_content(subdir: str, filename: str):
    path = os.path.join(CONTENT_DIR, subdir, filename)
    if not os.path.exists(path):
        return HTMLResponse("<h1>File not found</h1>", status_code=404)
    content = _read_file(path)
    if filename.endswith(".json"):
        return HTMLResponse(f"<pre>{content}</pre>")
    return HTMLResponse(f"<pre style='white-space: pre-wrap; font-family: monospace; padding: 20px;'>{content}</pre>")


@app.get("/api/stats")
async def api_stats():
    return JSONResponse({
        "bios": len(_list_content("bios")),
        "blog_posts": len(_list_content("blog_posts")),
        "interview_questions": len(_list_content("interview_questions")),
        "social_posts": len(_list_content("social_posts")),
        "email_templates": len(_list_content("email_templates")),
        "seo_keywords": len(_list_content("seo_keywords", "json")),
        "mass_analyses": len([a for a in _list_content("", "md") if "mass_analysis" in a["filename"]]),
    })


@app.get("/api/content/{subdir}")
async def api_list_content(subdir: str):
    ext = "json" if subdir == "seo_keywords" else "md"
    return JSONResponse(_list_content(subdir, ext))


def main():
    parser = argparse.ArgumentParser(description="RentMasseur Dashboard Server")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    logger.info("Starting dashboard at http://%s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
