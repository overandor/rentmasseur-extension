---
title: RentMasseur RevenueOps Control Plane
emoji: 🧾
colorFrom: purple
colorTo: blue
sdk: docker
pinned: false
---

# RentMasseur RevenueOps Control Plane

Production-control HF Docker Space for first-party RentMasseur profile experimentation.

Mission: **one paying client per day, or prove exactly why it failed today.**

This repo is not an automated login bot, CAPTCHA bypass tool, or fake-success dashboard. The runtime is evidence-only: no metric, no optimization; no receipt, no reality; no lead, no client claim.

## Production safety rules

- No automated platform login.
- No CAPTCHA fighting.
- No fake availability.
- No unattended profile mutation.
- No cookies, bearer tokens, passwords, sessions, or `.env` files in git or HF runtime.
- Only first-party/manual metric capture.
- Only approved bio experiments.
- Only receipt-backed actions.
- Live profile changes require human approval and a platform-compliant path.

## Runtime

The Docker Space builds the native C++ control plane:

- `cpp_os_server.cpp` → C++ HTTP RevenueOps server
- `rotator_engine.cpp` → candidate rotation engine
- `ga_rl_optimizer.cpp` → offline candidate optimizer
- `production_control_loop.cpp` → production decision gate

The Dockerfile compiles the native binaries and starts:

```bash
./cpp_os_server 7860
```

## Core API

Read-only endpoints:

```text
GET  /api/health
GET  /api/report
GET  /api/bios
GET  /api/candidates
GET  /api/funnel/daily
GET  /api/leads
GET  /api/decision/latest
GET  /api/jobs
GET  /api/receipts
GET  /api/audit/files
GET  /api/cicd/list
GET  /api/cicd/runs
```

Mutation endpoints require `ADMIN_TOKEN` and `Authorization: Bearer <ADMIN_TOKEN>`:

```text
POST /api/metrics/ingest
POST /api/config
GET  /api/rotate/{type}
GET  /api/run/ga-rl
GET  /api/run/orchestrator
GET  /api/rotator/report
GET  /api/cicd/trigger/{workflow}
```

`/api/run/availability` is intentionally blocked. The old live-login availability keeper is legacy/quarantined and must not be used as the production path.

## Metrics ingest

Only submit sanitized first-party/manual dashboard metrics. Do not submit cookies, tokens, passwords, sessions, raw API headers, or browser storage.

Example:

```json
{
  "date": "2026-06-26",
  "bio_id": "current_live_wolf_appended",
  "profile_views": 2802,
  "contact_clicks": 135,
  "new_visits": 31,
  "new_emails": 0,
  "online_bookmarks": 1,
  "public_visits": 78062,
  "days_online": 964,
  "views_per_day": 81.0,
  "profile_visible": true,
  "available": true
}
```

The server normalizes accepted metrics, writes `content/metrics_ingest.jsonl`, updates `content/metrics_latest.json`, and writes a receipt.

## Candidate workflow

Production should keep a small candidate pool, not a content firehose.

Initial approved archetypes:

1. Controlled Wolf
2. Clinical Recovery
3. Luxury Concierge
4. Direct Same-Day CTA

Run one live experiment at a time. Freeze photos, price, services, interview, blog, and availability while testing a bio.

Decision order:

```text
confirmed booking > booking request > phone click > email click > contact click > profile view
```

Views alone do not win. A bio that gets views but no contact actions loses.

## Repository layout

```text
/
  Dockerfile
  README.md
  .dockerignore

/src target currently lives at repo root for HF compatibility:
  cpp_os_server.cpp
  production_control_loop.cpp
  rotator_engine.cpp
  ga_rl_optimizer.cpp

/content
  bios/current_candidates.json
  metrics_ingest.jsonl     # runtime-generated; do not commit secrets
  metrics_latest.json      # runtime-generated
  decisions/latest_decision.json

/extension
  manifest.json
  content.js
  content.css
  popup.html
  popup.js

/legacy or quarantine candidates
  server.py
  checker.py
  rentmasseur_availability.py
  Selenium login scripts
```

## Extension role

The browser extension should be a first-party/manual capture tool only:

- capture dashboard stats while the operator is logged in
- capture active bio/version metadata
- export sanitized metrics
- send approved metrics to `/api/metrics/ingest`

It should not bypass platform controls or run unattended account mutation.

## Secret handling

Never commit or deploy:

- `.env`
- `session.json`
- cookies
- bearer tokens
- API headers
- browser storage dumps
- raw API maps containing auth material
- large raw traffic corpora

If a token or session file was pasted or uploaded into a chat/log/repo, treat it as burned and rotate/log out.
