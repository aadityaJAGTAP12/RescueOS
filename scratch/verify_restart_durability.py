"""
Process Restart Durability Verification (Item #7, Section 12)

Proves that all core entities survive a complete process termination and restart
against real PostgreSQL:
- Need
- ResourceOffer
- Coordination Proposal
- Notification
- ActivityEvent
"""

import os
import sys
import uuid
import subprocess
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_URL"] = "postgresql://reliefos:reliefos@localhost:5433/reliefos"
os.environ.pop("RELIEFOS_MEMORY", None)

from agent.data.models import Need, ResourceOffer, Notification, ActivityEvent, Organization
from agent.data.postgres_repository import PostgresRepository

def stage1_write():
    suffix = uuid.uuid4().hex[:6]
    test_data = {
        "need_id": f"need_restart_{suffix}",
        "offer_id": f"offer_restart_{suffix}",
        "prop_id": f"prop_restart_{suffix}",
        "notif_id": f"notif_restart_{suffix}",
        "event_id": f"evt_restart_{suffix}",
        "org_id": f"org_restart_{suffix}",
    }
    
    repo = PostgresRepository(database_url="postgresql://reliefos:reliefos@localhost:5433/reliefos")
    
    # Write Organization
    repo.create_organization(Organization(
        id=test_data["org_id"],
        name="Restart Org",
        organization_type="ngo",
    ))
    
    # Write Need
    repo.create_need(Need(
        id=test_data["need_id"],
        need_type="medical",
        title=f"Restart Test Need {suffix}",
        district_id="jorhat",
        urgency="high",
        status="OPEN",
    ))
    
    # Write Offer
    repo.create_resource_offer(ResourceOffer(
        id=test_data["offer_id"],
        organization_id=test_data["org_id"],
        resource_type="medical_kit",
        quantity=25,
        unit="kits",
        district_id="jorhat",
        status="OFFERED",
    ))
    
    # Write Proposal
    repo.create_proposal({
        "id": test_data["prop_id"],
        "need_id": test_data["need_id"],
        "organization_id": test_data["org_id"],
        "organization_name": "Restart Org",
        "proposal_type": "medical_support",
        "summary": "Restart test proposal summary",
        "status": "PROPOSED",
    })
    
    # Write Notification
    repo.create_notification(Notification(
        id=test_data["notif_id"],
        recipient_id=test_data["org_id"],
        notification_type="coordination_proposed",
        title="Restart Notif",
        message="Testing restart persistence",
        entity_type="coordination",
        entity_id=test_data["prop_id"],
        read=False,
    ))
    
    # Write ActivityEvent
    repo.append_activity_event(ActivityEvent(
        id=test_data["event_id"],
        entity_type="coordination",
        entity_id=test_data["prop_id"],
        event_type="coordination_proposed",
        actor=test_data["org_id"],
        detail="Proposal recorded for restart test",
    ))
    
    # Save ids to temp file
    manifest_path = os.path.join(os.path.dirname(__file__), "restart_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(test_data, f)
    print(f"Stage 1: Successfully wrote all entities to PostgreSQL. Manifest written to {manifest_path}")

def stage2_read():
    manifest_path = os.path.join(os.path.dirname(__file__), "restart_manifest.json")
    with open(manifest_path, "r") as f:
        test_data = json.load(f)
    
    # Fresh connection & repository in separate process
    repo = PostgresRepository(database_url="postgresql://reliefos:reliefos@localhost:5433/reliefos")
    
    # Verify Need
    need = repo.get_need(test_data["need_id"])
    assert need is not None, f"Need {test_data['need_id']} not found in fresh process"
    assert need.district_id == "jorhat"
    print(f"[OK] Need {need.id} successfully read in fresh process: {need.title}")
    
    # Verify Offer
    offer = repo.get_resource_offer(test_data["offer_id"])
    assert offer is not None, f"Offer {test_data['offer_id']} not found in fresh process"
    assert offer.quantity == 25
    print(f"[OK] ResourceOffer {offer.id} successfully read in fresh process: {offer.resource_type}")
    
    # Verify Proposal
    prop = repo.get_proposal(test_data["prop_id"])
    assert prop is not None, f"Proposal {test_data['prop_id']} not found in fresh process"
    assert prop["status"] == "PROPOSED"
    print(f"[OK] Coordination Proposal {prop['id']} successfully read in fresh process: {prop['status']}")
    
    # Verify Notification
    notifs = repo.list_notifications(recipient_id=test_data["org_id"])
    assert any(n.id == test_data["notif_id"] for n in notifs), f"Notification {test_data['notif_id']} not found"
    print(f"[OK] Notification {test_data['notif_id']} successfully read in fresh process")
    
    # Verify ActivityEvent
    events = repo.list_activity_events(entity_type="coordination", entity_id=test_data["prop_id"])
    assert any(e.id == test_data["event_id"] for e in events), f"ActivityEvent {test_data['event_id']} not found"
    print(f"[OK] ActivityEvent {test_data['event_id']} successfully read in fresh process")
    
    print("\n=== RESTART PERSISTENCE VERIFICATION 100% SUCCESSFUL ===")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "stage1":
        stage1_write()
    elif len(sys.argv) > 1 and sys.argv[1] == "stage2":
        stage2_read()
    else:
        print("Usage: python verify_restart_durability.py [stage1|stage2]")
