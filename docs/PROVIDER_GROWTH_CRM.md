# Provider Growth CRM

Provider Growth CRM turns the availability script into a local operator console for account-owned growth workflows.

It is manual-first, receipt-backed, and policy-gated. It stores engagement records, profile content versions, draft suggestions, outbox state, iMac/Mac handoff files, conversion snapshots, revenue events, and receipts. It does not bypass access controls, collect hidden data, or transmit outbound content without human approval.

## Modules

- `provider_growth/db.py` — SQLite schema, default policy seed, indexes.
- `provider_growth/receipts.py` — JSONL + SQLite audit receipts.
- `provider_growth/engagement.py` — manual engagement records and scoring.
- `provider_growth/drafts.py` — reviewable draft queue.
- `provider_growth/policy.py` — approval, quiet-hour, and do-not-contact policy gate.
- `provider_growth/outbox.py` — manual outbox state machine: queued, ready, blocked, exported, completed.
- `provider_growth/kpi.py` — revenue events and funnel liquidity summary.
- `provider_growth/profile_content.py` — bio, blog, interview, headline, and availability-note versions.
- `provider_growth/experiments.py` — daily conversion snapshots and version summaries.
- `provider_growth/imac_relay.py` — local manual handoff files for Mac review workflows.
- `provider_growth_cli.py` — command-line console.

## Production-shaped workflow

```bash
python provider_growth_cli.py init-db
python provider_growth_cli.py policy
python provider_growth_cli.py add-record "manual-client-handle" --name "Client"
python provider_growth_cli.py priority-records
python provider_growth_cli.py draft <record_key> --template same_day --name "Client" --channel imessage
python provider_growth_cli.py evaluate-draft <draft_id>
python provider_growth_cli.py approve-draft <draft_id>
python provider_growth_cli.py enqueue <draft_id>
python provider_growth_cli.py outbox --state ready
python provider_growth_cli.py export-outbox <outbox_id>
python provider_growth_cli.py complete-outbox <outbox_id> --outcome manual_completed
python provider_growth_cli.py add-version bio bio_v1 "Profile text here" --reason "trust-focused version"
python provider_growth_cli.py activate-version <version_id>
python provider_growth_cli.py snapshot --version bio_v1 --views 50 --repeat 6 --contacts 4 --inbound 3 --bookings 1
python provider_growth_cli.py revenue-event confirmed_booking --amount-cents 20000 --record-key <record_key>
python provider_growth_cli.py revenue-summary
```

## State model

Draft states:

```text
draft -> approved -> queued/outbox -> exported -> manual_completed
                  \-> blocked
                  \-> skipped
                  \-> failed
```

Policy decisions:

```text
needs_approval
allowed
blocked
defer
```

Revenue events:

```text
inquiry
quote
booking_request
confirmed_booking
completed_booking
cancelled
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
- approved local handoff files
- manually logged revenue events

Not allowed:

- automated spam
- hidden data collection
- account access without authorization
- challenge/captcha bypass
- sending without explicit human approval
- fake availability

## Revenue loop

Availability keeps the profile open for demand. Engagement records identify warm demand. Drafts keep conversations organized. Policy gates prevent sloppy action. Outbox creates an operator queue. iMac handoff turns an approved draft into a local review file. Profile versions test positioning. Metrics show which content creates contact actions and bookings. Revenue events turn conversations into pipeline. Receipts prove what happened.
