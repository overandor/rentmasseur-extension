# RentMasseur Booker Extension + Availability CI/CD

Chrome extension that adds a booking panel to RentMasseur.com profile pages, backed by a scheduled CI/CD availability checker.

## Architecture

1. **CI/CD checker** (`checker.py` + `.github/workflows/availability.yml`) runs on a schedule and scrapes the configured provider list, recording observed availability in `availability.json`.
2. **API server** (`server.py`) serves `availability.json` over `/api/availability/{slug}` and hosts `widget.html` / `verify.html` landing pages.
3. **Chrome extension** (`content.js`) injects the booking panel, reads the slug from the RentMasseur URL, and fetches the latest availability from the API server.

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

## Requirements

- API server must be running on the configured URL
- Chrome 88+ (Manifest V3)
- Python 3.11+ with `requests`, `beautifulsoup4`, `fastapi`, `uvicorn`
