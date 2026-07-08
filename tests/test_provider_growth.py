import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from provider_growth.db import init_db
from provider_growth.drafts import approve_draft, create_draft
from provider_growth.engagement import upsert_record
from provider_growth.experiments import add_snapshot, summarize_by_version
from provider_growth.imac_relay import export_manual_handoff, open_conversation_record, log_conversation_event
from provider_growth.profile_content import activate_version, add_version


def test_provider_growth_full_manual_loop(tmp_path):
    db_path = str(tmp_path / "growth.sqlite3")
    handoff_dir = str(tmp_path / "handoffs")
    init_db(db_path)

    record = upsert_record("authorized-record-1", display_name="Client", db_path=db_path)
    assert record["record_key"]
    assert record["score"] >= 0

    draft = create_draft(record["record_key"], "same_day", name="Client", channel="imessage", db_path=db_path)
    assert draft["approval_required"] is True
    assert draft["status"] == "draft"

    approved = approve_draft(draft["draft_id"], db_path=db_path)
    assert approved["draft"]["status"] == "approved"

    handoff = export_manual_handoff(draft["draft_id"], output_dir=handoff_dir, db_path=db_path)
    assert Path(handoff["path"]).exists()

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
