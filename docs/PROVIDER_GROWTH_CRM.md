# Provider Growth CRM

Provider Growth CRM turns the availability script into a local operator console for account-owned growth workflows.

It is intentionally manual-first. It stores engagement records, profile content versions, draft suggestions, iMac handoff files, conversion snapshots, and receipts. It does not bypass access controls, collect hidden data, or transmit outbound content without human approval.

## Modules

- `provider_growth/db.py` — SQLite schema.
- `provider_growth/receipts.py` — JSONL + SQLite audit receipts.
- `provider_growth/engagement.py` — manual engagement records and scoring.
- `provider_growth/drafts.py` — reviewable draft queue.
- `provider_growth/profile_content.py` — bio, blog, interview, headline, and availability-note versions.
- `provider_growth/experiments.py` — daily conversion snapshots and version summaries.
- `provider_growth/imac_relay.py` — local manual handoff files for Mac review workflows.
- `provider_growth_cli.py` — command-line console.

## Workflow

```bash
python provider_growth_cli.py init-db
python provider_growth_cli.py add-record "manual-client-handle" --name "Client"
python provider_growth_cli.py priority-records
python provider_growth_cli.py draft <record_key> --template same_day --name "Client" --channel imessage
python provider_growth_cli.py approve-draft <draft_id>
python provider_growth_cli.py handoff <draft_id>
python provider_growth_cli.py add-version bio bio_v1 "Profile text here" --reason "trust-focused version"
python provider_growth_cli.py activate-version <version_id>
python provider_growth_cli.py snapshot --version bio_v1 --views 50 --repeat 6 --contacts 4 --inbound 3 --bookings 1
python provider_growth_cli.py summary
```

## Compliance boundary

Allowed:

- account-owner records
- manual imports
- human-reviewed drafts
- opt-out / do-not-contact handling
- local receipts
- content versioning
- conversion measurement

Not allowed:

- automated spam
- hidden data collection
- account access without authorization
- challenge/captcha bypass
- sending without explicit human approval
- fake availability

## Revenue loop

Availability keeps the profile open for demand. Engagement records identify warm demand. Drafts keep conversations alive. Profile versions test content. Metrics show which content creates contact actions and bookings. Receipts prove what happened.
