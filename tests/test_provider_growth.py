import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from provider_growth.db import init_db
from provider_growth.drafts import approve_draft, create_draft
from provider_growth.engagement import upsert_record
from provider_growth.experiments import add_snapshot, summarize_by_version
from provider_growth.imac_relay import open_conversation_record, log_conversation_event
from provider_growth.kpi import add_revenue_event, revenue_summary
from provider_growth.outbox import enqueue_draft, export_ready_item, mark_completed
from provider_growth.policy import evaluate_and_receipt, set_policy
from provider_growth.profile_content import activate_version, add_version


def test_provider_growth_production_manual_loop(tmp_path):
    db_path = str(tmp_path / "growth.sqlite3")
    outbox_dir = str(tmp_path / "outbox")
    init_db(db_path)

    # Avoid local quiet-hour timing in deterministic tests.
    set_policy("quiet_hours_start", "23", db_path=db_path)
    set_policy("quiet_hours_end", "0", db_path=db_path)

    record = upsert_record("authorized-record-1", display_name="Client", db_path=db_path)
    assert record["record_key"]
    assert record["score"] >= 0

    draft = create_draft(record["record_key"], "same_day", name="Client", channel="imessage", db_path=db_path)
    assert draft["approval_required"] is True
    assert draft["status"] == "draft"

    blocked = evaluate_and_receipt(draft["draft_id"], db_path=db_path)
    assert blocked["decision"] == "needs_approval"

    approved = approve_draft(draft["draft_id"], db_path=db_path)
    assert approved["draft"]["status"] == "approved"

    allowed = evaluate_and_receipt(draft["draft_id"], db_path=db_path)
    assert allowed["allowed"] is True

    outbox = enqueue_draft(draft["draft_id"], db_path=db_path)
    assert outbox["state"] == "ready"

    exported = export_ready_item(outbox["outbox_id"], output_dir=outbox_dir, db_path=db_path)
    assert Path(exported["path"]).exists()

    completed = mark_completed(outbox["outbox_id"], db_path=db_path)
    assert completed["state"] == "manual_completed"

    conversation = open_conversation_record(record["record_key"], channel="imessage", db_path=db_path)
    event = log_conversation_event(conversation["conversation_id"], "note", "manual review completed", db_path=db_path)
    assert event["direction"] == "note"

    version = add_version("bio", "bio_v1", "Calm, professional profile text.", reason="trust version", db_path=db_path)
    activated = activate_version(version["version_id"], db_path=db_path)
    assert activated["status"] == "active"

    add_snapshot(profile_version_label="bio_v1", profile_views=10, repeat_visitors=2, contact_actions=1, inbound_messages=1, booking_requests=1, db_path=db_path)
    summary = summarize_by_version(db_path=db_path)
    assert summary[0]["profile_version_label"] == "bio_v1"
    assert summary[0]["booking_requests"] == 1

    add_revenue_event("confirmed_booking", amount_cents=20000, visitor_key=record["record_key"], db_path=db_path)
    kpi = revenue_summary(db_path=db_path)
    assert kpi["confirmed_pipeline_usd"] == 200.0
    assert kpi["outbox_by_state"]["manual_completed"] == 1
