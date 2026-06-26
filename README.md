# RentMasseur Booker Extension + Availability CI/CD

Chrome extension that adds a booking panel to RentMasseur.com profile pages, backed by a scheduled CI/CD availability checker.

## Architecture

1. **CI/CD checker** (`checker.py` + `.github/workflows/availability.yml`) runs on a schedule and scrapes the configured provider list, recording observed availability in `availability.json`.
2. **API server** (`server.py`) serves `availability.json` over `/api/availability/{slug}` and hosts `widget.html` / `verify.html` landing pages.
3. **Chrome extension** (`content.js`) injects the booking panel, reads the slug from the RentMasseur URL, and fetches the latest availability from the API server.
4. **Optimizer automation** (`rentmasseur_optimizer.py`, `rentmasseur_core.py`, `rentmasseur_coordinator.py`, `rentmasseur_availability.py`, `intent_router.py`) uses Selenium to log in, keep your own availability set to 24/7, and generate/update your profile bio via Groq LLM.

## Install the extension

1. Open Chrome → `chrome://extensions/`
2. Enable **Developer mode** (toggle top-right)
3. Click **Load unpacked**
4. Select this folder (`rentmasseur-extension`)

## Run the API server locally

```bash
python3 -m uvicorn server:app --host 127.0.0.1 --port 3000
```

To seed mock data for testing:

```bash
python3 checker.py --mock --output availability.json
```

## Run the availability checker

```bash
python3 checker.py --output availability.json
```

For CI/CD mock mode:

```bash
python3 checker.py --mock --output availability.json
```

## Run the optimizer (logged-in profile automation)

Requires a `.env` file with your RentMasseur and Groq credentials (see `.env.example`).

```bash
cp .env.example .env
# edit .env with your credentials
python3 rentmasseur_optimizer.py
```

Keep availability 24/7 only:

```bash
python3 rentmasseur_availability.py
```

Run the coordinator with intent routing to pick top bio strategies:

```bash
python3 rentmasseur_coordinator.py --pick-best --top-n 5
```

## Autonomous CI/CD 24/7 availability keeper

The repo includes `.github/workflows/availability-keeper.yml` which runs every 5 minutes (GitHub's fastest schedule) and logs into your RentMasseur account to keep availability set to 24/7. No mock data, no simulation — it uses real Selenium automation against the live site.

Required GitHub secrets (Settings → Secrets and variables → Actions):

- `RENTMASSEUR_USERNAME`
- `RENTMASSEUR_PASSWORD`

You can also run the keeper in a tight local loop:

```bash
python3 rentmasseur_availability.py --interval 1
```

## Daily content generation (bios, blog posts, interview questions)

The repo includes `.github/workflows/daily-content.yml` which runs every day at 6:00 UTC and generates:

- **30 bios** — one per strategy, optimized for conversion
- **30 blog posts** — SEO-optimized, 500-800 words each
- **30 interview question sets** — 10 Q&A per strategy for PR use
- **Mass analysis report** — ranks the best versions across all strategies

All content is committed to the `content/` directory automatically.

Run locally:

```bash
python3 content_generator.py                    # everything
python3 content_generator.py --bios-only        # bios only
python3 content_generator.py --blogs-only       # blog posts only
python3 content_generator.py --questions-only   # interview questions only
```

## What it does

- Detects when you view a masseur profile on `rentmasseur.com`
- Shows a floating panel with:
  - Provider name & location (auto-extracted from page)
  - Availability status from the CI/CD API (`live` or `mock` badge)
  - **"Book Now"** button → opens `widget.html` with provider info pre-filled
  - **"Verify Video Call"** button → opens `verify.html`
  - **"Check Availability"** button → fetches latest availability from the API
- Works with SPA navigation (Next.js / React Router)

## Configuration

Click the extension icon in the toolbar → set your **Booking Server URL** (default: `http://localhost:3000`)

## Files

| File | Purpose |
|---|---|
| `manifest.json` | Extension manifest (MV3) |
| `content.js` | Injects booking panel and fetches availability API |
| `content.css` | Panel styling |
| `popup.html` / `popup.js` | Extension popup settings |
| `checker.py` | Scheduled availability scraper |
| `providers.json` | Provider list to monitor |
| `availability.json` | Latest observed availability |
| `server.py` | FastAPI availability + booking landing server |
| `.github/workflows/availability.yml` | GitHub Actions CI/CD workflow |
| `rentmasseur_optimizer.py` | Full optimizer: availability + bio update |
| `rentmasseur_availability.py` | Standalone 24/7 availability keeper |
| `rentmasseur_coordinator.py` | Strategy coordinator with intent routing |
| `rentmasseur_core.py` | Shared Selenium driver, login, bio utilities |
| `intent_router.py` | Groq-based strategy selection |
| `content_generator.py` | Daily bios, blog posts, interview questions + mass analysis |
| `.env.example` | Required environment variables |

## Requirements

- API server must be running on the configured URL
- Chrome 88+ (Manifest V3)
- Python 3.11+ with `requests`, `beautifulsoup4`, `fastapi`, `uvicorn`
- For optimizer automation: `selenium`, `python-dotenv`, `playwright`, and a Groq API key
