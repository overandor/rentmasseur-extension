#!/usr/bin/env python3
"""Provider Growth CRM command line.

Everything here is local/manual-first. It creates records, drafts, policy
decisions, outbox handoffs, content versions, metrics, receipts, and revenue
ledger events. It does not transmit messages or perform unattended outreach.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from provider_growth.db import DEFAULT_DB_PATH, init_db
from provider_growth.drafts import approve_draft, create_draft, list_drafts
from provider_growth.engagement import list_priority_records, upsert_record
from provider_growth.experiments import add_snapshot, summarize_by_version
from provider_growth.imac_relay import export_manual_handoff, list_conversations, log_conversation_event, open_conversation_record
from provider_growth.kpi import add_revenue_event, revenue_summary
from provider_growth.outbox import enqueue_draft, export_ready_item, list_outbox, mark_completed
from provider_growth.policy import evaluate_and_receipt, get_policy, set_policy
from provider_growth.profile_content import activate_version, add_version, list_versions


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Provider Growth CRM")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")
    sub.add_parser("policy")

    set_pol = sub.add_parser("set-policy")
    set_pol.add_argument("key")
    set_pol.add_argument("value")
    set_pol.add_argument("--description", default="")

    eval_pol = sub.add_parser("evaluate-draft")
    eval_pol.add_argument("draft_id", type=int)

    add_record = sub.add_parser("add-record")
    add_record.add_argument("identifier")
    add_record.add_argument("--name")
    add_record.add_argument("--source", default="manual")

    hot = sub.add_parser("priority-records")
    hot.add_argument("--min-score", type=int, default=3)
    hot.add_argument("--limit", type=int, default=25)

    draft = sub.add_parser("draft")
    draft.add_argument("record_key")
    draft.add_argument("--template", default="soft_checkin")
    draft.add_argument("--name", default="there")
    draft.add_argument("--channel", default="manual")

    approve = sub.add_parser("approve-draft")
    approve.add_argument("draft_id", type=int)

    drafts = sub.add_parser("drafts")
    drafts.add_argument("--status", default="draft")

    enqueue = sub.add_parser("enqueue")
    enqueue.add_argument("draft_id", type=int)

    outbox = sub.add_parser("outbox")
    outbox.add_argument("--state")

    export_item = sub.add_parser("export-outbox")
    export_item.add_argument("outbox_id", type=int)
    export_item.add_argument("--output-dir", default="data/manual_outbox")

    complete = sub.add_parser("complete-outbox")
    complete.add_argument("outbox_id", type=int)
    complete.add_argument("--outcome", default="manual_completed", choices=["manual_completed", "skipped", "failed"])

    handoff = sub.add_parser("handoff")
    handoff.add_argument("draft_id", type=int)
    handoff.add_argument("--output-dir", default="data/imac_handoffs")

    conv = sub.add_parser("open-conversation")
    conv.add_argument("record_key")
    conv.add_argument("--handle")
    conv.add_argument("--channel", default="imessage")

    log_event = sub.add_parser("log-event")
    log_event.add_argument("conversation_id", type=int)
    log_event.add_argument("direction", choices=["inbound", "outbound", "note"])
    log_event.add_argument("body")

    sub.add_parser("conversations")

    version = sub.add_parser("add-version")
    version.add_argument("field_name", choices=["bio", "blog", "interview", "availability_note", "headline"])
    version.add_argument("label")
    version.add_argument("content")
    version.add_argument("--reason", default="")

    activate = sub.add_parser("activate-version")
    activate.add_argument("version_id", type=int)

    versions = sub.add_parser("versions")
    versions.add_argument("--field")

    metrics = sub.add_parser("snapshot")
    metrics.add_argument("--version")
    metrics.add_argument("--views", type=int, default=0)
    metrics.add_argument("--repeat", type=int, default=0)
    metrics.add_argument("--contacts", type=int, default=0)
    metrics.add_argument("--inbound", type=int, default=0)
    metrics.add_argument("--bookings", type=int, default=0)

    rev = sub.add_parser("revenue-event")
    rev.add_argument("event_type", choices=["inquiry", "quote", "booking_request", "confirmed_booking", "completed_booking", "cancelled"])
    rev.add_argument("--amount-cents", type=int, default=0)
    rev.add_argument("--record-key")
    rev.add_argument("--source", default="manual")
    rev.add_argument("--notes", default="")

    sub.add_parser("summary")
    sub.add_parser("revenue-summary")

    args = parser.parse_args()

    if args.command == "init-db":
        init_db(args.db)
        print_json({"ok": True, "db": args.db})
    elif args.command == "policy":
        print_json(get_policy(args.db))
    elif args.command == "set-policy":
        print_json(set_policy(args.key, args.value, args.description, db_path=args.db))
    elif args.command == "evaluate-draft":
        print_json(evaluate_and_receipt(args.draft_id, db_path=args.db))
    elif args.command == "add-record":
        print_json(upsert_record(args.identifier, display_name=args.name, source=args.source, db_path=args.db))
    elif args.command == "priority-records":
        print_json(list_priority_records(args.min_score, args.limit, db_path=args.db))
    elif args.command == "draft":
        print_json(create_draft(args.record_key, args.template, args.name, args.channel, db_path=args.db))
    elif args.command == "approve-draft":
        print_json(approve_draft(args.draft_id, db_path=args.db))
    elif args.command == "drafts":
        print_json(list_drafts(args.status, db_path=args.db))
    elif args.command == "enqueue":
        print_json(enqueue_draft(args.draft_id, db_path=args.db))
    elif args.command == "outbox":
        print_json(list_outbox(args.state, db_path=args.db))
    elif args.command == "export-outbox":
        print_json(export_ready_item(args.outbox_id, args.output_dir, db_path=args.db))
    elif args.command == "complete-outbox":
        print_json(mark_completed(args.outbox_id, args.outcome, db_path=args.db))
    elif args.command == "handoff":
        print_json(export_manual_handoff(args.draft_id, args.output_dir, db_path=args.db))
    elif args.command == "open-conversation":
        print_json(open_conversation_record(args.record_key, args.handle, args.channel, db_path=args.db))
    elif args.command == "log-event":
        print_json(log_conversation_event(args.conversation_id, args.direction, args.body, db_path=args.db))
    elif args.command == "conversations":
        print_json(list_conversations(db_path=args.db))
    elif args.command == "add-version":
        print_json(add_version(args.field_name, args.label, args.content, args.reason, db_path=args.db))
    elif args.command == "activate-version":
        print_json(activate_version(args.version_id, db_path=args.db))
    elif args.command == "versions":
        print_json(list_versions(args.field, db_path=args.db))
    elif args.command == "snapshot":
        print_json(add_snapshot(args.version, args.views, args.repeat, args.contacts, args.inbound, args.bookings, db_path=args.db))
    elif args.command == "revenue-event":
        print_json(add_revenue_event(args.event_type, args.amount_cents, args.record_key, source=args.source, notes=args.notes, db_path=args.db))
    elif args.command == "summary":
        print_json(summarize_by_version(db_path=args.db))
    elif args.command == "revenue-summary":
        print_json(revenue_summary(db_path=args.db))


if __name__ == "__main__":
    main()
