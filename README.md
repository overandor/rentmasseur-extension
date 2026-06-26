---
title: RentMasseur RevenueOps
emoji: 🚀
colorFrom: purple
colorTo: blue
sdk: docker
pinned: false
---

# RentMasseur RevenueOps Control Plane

Approval-gated RevenueOps control plane for RentMasseur profile optimization.

## What This Repo Does

- **C++ control plane** (`cpp_os_server.cpp`) — native HTTP server on port 7860
- **Chrome extension** — first-party capture tool for profile metrics
- **Receipt-backed decisions** — every action writes a tamper-evident receipt
- **Controlled bio experiments** — one approved candidate at a time, with frozen variables

## What This Repo Does NOT Do

- No automated platform login
- No CAPTCHA fighting or anti-bot bypass
- No fake 24/7 availability claims
- No unattended profile mutation
- No mass content generation to the live profile

## Safety Rules

1. Only first-party/manual metric capture
2. Only approved bio experiments
3. Only receipt-backed changes
4. All mutation endpoints require `ADMIN_TOKEN` (Bearer auth)
5. No query-string token auth (prevents log leaks)
6. Empty `ADMIN_TOKEN` blocks all mutations

## API Endpoints

### Read-only (no auth required)
- `GET /api/health` — server health
- `GET /api/report` — system report
- `GET /api/bios` — current bio candidates
- `GET /api/candidates` — candidate pool
- `GET /api/decision/latest` — latest decision
- `GET /api/funnel/daily` — daily funnel metrics
- `GET /api/receipts` — receipt ledger
- `GET /api/metrics/ingest` — metrics history

### Mutation (requires `ADMIN_TOKEN`)
- `POST /api/metrics/ingest` — ingest daily metrics (no auth required for data ingestion)
- `POST /api/run/ga-rl` — run GA+RL optimization
- `POST /api/run/orchestrator` — run orchestrator
- `POST /api/run/availability` — BLOCKED (automation disabled)

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ADMIN_TOKEN` | Yes | Bearer token for mutation endpoints |

## Docker Deployment

```bash
docker build -t rm-revenueops .
docker run -p 7860:7860 -e ADMIN_TOKEN="your-secret-token" rm-revenueops
```

## Chrome Extension

The extension (`manifest.json`, `content.js`, `popup.html`) adds a metrics capture panel to RentMasseur.com profile pages. It reads dashboard data manually — no automated login.

## Experiment Workflow

1. Capture dashboard metrics manually or via extension
2. Ingest metrics via `POST /api/metrics/ingest`
3. Review candidates at `GET /api/candidates`
4. Start experiment via `POST /api/experiments/start` (requires ADMIN_TOKEN)
5. Wait 100+ new profile views or 24-48 hours
6. Close experiment and compute lift
7. Decision: `KEEP_CURRENT`, `WINNER_FOUND`, `REVERT_TO_BASELINE`, or `NO_SIGNAL`

## File Structure

```
/
  Dockerfile
  README.md
  .dockerignore
  cpp_os_server.cpp          — C++ control plane
  rotator_engine.cpp         — rotation engine
  ga_rl_optimizer.cpp        — GA+RL optimizer
  production_control_loop.cpp — production loop
  manifest.json              — Chrome extension
  content.js                 — extension content script
  popup.html / popup.js      — extension popup
  content/
    bios/current_candidates.json — 4 approved bio candidates
    metrics/                   — ingested metrics
  receipts/                   — tamper-evident receipt chain
```
