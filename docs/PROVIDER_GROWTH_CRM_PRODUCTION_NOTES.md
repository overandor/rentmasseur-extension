# Provider Growth CRM Production Notes

This branch is no longer just a toy CRM scaffold. It now has a production-shaped local operator model:

1. Local SQLite ledger.
2. Default policy seed.
3. Manual approval gate.
4. Quiet-hour gate.
5. Do-not-contact gates.
6. Manual outbox state machine.
7. Approved local handoff export.
8. Conversation event receipts.
9. Profile content versioning.
10. Funnel and revenue liquidity KPIs.

## Non-negotiable constraints

The system is not an auto-sender. It is a local operator queue. The operator remains responsible for reviewing and performing any outbound action.

The system is not a hidden-data collector. Records must come from sources the operator owns, controls, or is authorized to manage.

The system is not a challenge/captcha bypass tool.

## Real operating loop

```text
record demand signal
→ score record
→ create draft
→ approve draft
→ evaluate policy
→ enqueue outbox item
→ export manual handoff
→ operator reviews on Mac/iMac
→ operator completes/skips/fails item
→ log conversation note
→ update metrics snapshot
→ log revenue event
→ inspect revenue summary
```

## Why this is more serious

The previous version stored records and drafts. This version adds operational control:

- policy decisions are explicit
- handoff has a state machine
- revenue events are separate from vanity metrics
- every important action can create a receipt
- tests exercise the full approved outbox path

## Next production layer

To become production-grade, add:

- migration files instead of schema-in-code only
- encrypted local storage for sensitive aliases
- desktop UI or menu bar wrapper
- signed receipt chain
- calendar availability integration
- explicit consent/authorization intake for any managed account
- test fixtures with synthetic data
- macOS notification-only adapter
- backup/export command
