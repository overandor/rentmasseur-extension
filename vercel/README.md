# RentMasseur Vercel Backend

Serverless functions that collect metrics and proxy data to the Hugging Face Space OS.

## Deploy

```bash
cd vercel
vercel --prod
```

## Environment Variables

- `HF_SPACE_URL` — URL of the Hugging Face Space (e.g., `https://your-username-rentmasseur-optimizer.hf.space`)
- `HF_TOKEN` — optional HF token for private spaces

## Functions

- `POST /api/collect` — ingest metrics from extension
- `GET /api/report` — full OS report
- `GET /api/bios` — bio candidates
- `GET /api/competitors` — competitor intelligence
