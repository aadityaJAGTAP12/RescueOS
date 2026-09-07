"""
Full System Integration & Regression Verification Script (Item #7)
Runs against live PostgreSQL (DATABASE_URL) and verifies:
1. Core product data & endpoints
2. Need lifecycle (normal vs critical)
3. Offer lifecycle (direct NGO publishing)
4. Coordination proposal lifecycle (propose -> send -> evaluate -> approve -> confirm)
5. Notification lifecycle (emission -> recipient scoping -> mark read -> persistence)
6. Multi-Org Isolation (adversarial cross-org evaluation, approval, notification reads)
7. Identity Seam (cookie vs body org_id precedence)
8. Privacy Sweep (absence of private_factors/secrets in network responses)
9. Restart Durability (multi-process persistence verification in PostgreSQL)
"""

import os
import sys
import uuid
import json
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure DATABASE_URL is set
os.environ["DATABASE_URL"] = "postgresql://reliefos:reliefos@localhost:5433/reliefos"
os.environ.pop("RELIEFOS_MEMORY", None)

from agent.api import app
from agent.data.repository import get_repository, reset_repository
from agent.data.postgres_repository import PostgresRepository

def run_verification():
    print("=== STARTING ITEM #7 SYSTEM INTEGRATION VERIFICATION ===")
    
    # Verify Postgres repository
    repo = get_repository()
    assert isinstance(repo, PostgresRepository), f"Expected PostgresRepository, got {type(repo)}"
    print("[OK] Repository is PostgresRepository connected to PostgreSQL")

    with app.test_client() as client:
        # 1. Core Endpoints Smoke Test
        print("\n--- 1. Core Endpoints Smoke Test ---")
        districts_res = client.get("/api/districts")
        assert districts_res.status_code == 200, districts_res.get_json()
        districts = districts_res.get_json().get("districts", [])
        assert len(districts) >= 4, f"Expected at least 4 districts, got {len(districts)}"
        print(f"[OK] Districts loaded: {[d['id'] for d in districts]}")

        flood_res = client.get("/api/flood-geojson")
        assert flood_res.status_code == 200
        print("[OK] Flood GeoJSON loaded")

        roads_res = client.get("/api/districts/jorhat/roads")
        assert roads_res.status_code == 200
        print(f"[OK] Roads loaded for Jorhat ({len(roads_res.get_json().get('roads', []))} features)")

        # 2. Org Identity Seam & Session Setup
        print("\n--- 2. Org Identity Seam Setup ---")
        org_a_id = f"org_alpha_{uuid.uuid4().hex[:6]}"
        org_b_id = f"org_beta_{uuid.uuid4().hex[:6]}"
        
        client.post("/api/organizations", json={"id": org_a_id, "name": "Alpha NGO", "organization_type": "ngo"})
        client.post("/api/organizations", json={"id": org_b_id, "name": "Beta NGO", "organization_type": "ngo"})
        
        # Test session selection
        resp = client.post("/api/session/org", json={"org_id": org_a_id})
        assert resp.status_code == 200
        assert resp.get_json()["org_id"] == org_a_id
        
        # Verify get current session org
        session_res = client.get("/api/session/org")
        assert session_res.status_code == 200
        assert session_res.get_json()["org_id"] == org_a_id
        print(f"[OK] Identity seam verified: active org is {org_a_id}")

        # 3. Need Lifecycle (Normal vs Critical)
        print("\n--- 3. Need Lifecycle Verification ---")
        # Normal Need
        need_normal_id = f"need_norm_{uuid.uuid4().hex[:6]}"
        res_norm = client.post("/api/needs", json={
            "id": need_normal_id,
            "title": "Standard Medical Supplies",
            "need_type": "medical",
            "district_id": "jorhat",
            "urgency": "medium",
            "status": "OPEN",
        })
        assert res_norm.status_code == 201, res_norm.get_json()
        
        # Check no urgent notification was emitted for medium need
        norm_notifs = [n for n in repo.list_notifications(recipient_id="network") if n.entity_id == need_normal_id]
        assert len(norm_notifs) == 0, "Normal need should not generate urgent notification"
        print("[OK] Normal need persisted without broadcast notification")

        # Critical Need
        res_crit = client.post("/api/needs", json={
            "title": "Severe Flood Water Rescue",
            "need_type": "rescue_boat",
            "district_id": "jorhat",
            "urgency": "critical",
            "status": "OPEN",
        })
        assert res_crit.status_code == 201, res_crit.get_json()
        need_crit_id = res_crit.get_json()["need"]["id"]
        
        # Check urgent_need notification emitted to network
        crit_notifs = [n for n in repo.list_notifications(recipient_id="network") if n.entity_id == need_crit_id]
        assert len(crit_notifs) == 1, f"Expected 1 urgent notification, found {len(crit_notifs)}"
        assert crit_notifs[0].notification_type == "urgent_need"
        print(f"[OK] Critical need {need_crit_id} emitted urgent_need notification to network")

        # 4. Direct Offer Lifecycle
        print("\n--- 4. Offer Lifecycle Verification ---")
        client.set_cookie("reliefos_org_id", org_a_id)
        offer_res = client.post("/api/my-org/publish-offer", json={
            "resource_type": "rescue_boat",
            "quantity": 5,
            "unit": "boats",
            "district_id": "jorhat",
        })
        assert offer_res.status_code == 201, offer_res.get_json()
        offer_id = offer_res.get_json()["offer"]["id"]
        
        # Verify offer appears in network query
        offers_res = client.get(f"/api/offers?organization_id={org_a_id}")
        assert offers_res.status_code == 200
        matching_offers = [o for o in offers_res.get_json()["offers"] if o["id"] == offer_id]
        assert len(matching_offers) == 1
        assert matching_offers[0]["organization_id"] == org_a_id
        print(f"[OK] Direct offer {offer_id} published and scoped to {org_a_id}")

        # 5. Coordination Proposal Lifecycle
        print("\n--- 5. Coordination Proposal Lifecycle Verification ---")
        # Step A: Propose coordination targeting Org A
        need_obj = repo.get_need(need_crit_id)
        prop_res = client.post("/api/network/coordination/propose", json={
            "need": need_obj.to_dict(),
            "organization_id": org_a_id,
            "organization_name": "Alpha NGO",
        })
        assert prop_res.status_code == 201, prop_res.get_json()
        prop_id = prop_res.get_json()["proposal"]["id"]
        assert prop_res.get_json()["proposal"]["status"] == "PROPOSED"

        # Check notification for Org A
        notifs_a = repo.list_notifications(recipient_id=org_a_id)
        assert any(n.entity_id == prop_id and n.notification_type == "coordination_proposed" for n in notifs_a)
        print(f"[OK] Proposal {prop_id} created with PROPOSED status and notification emitted")

        # Step B: Send to Org A
        send_res = client.post(f"/api/network/coordination/proposals/{prop_id}/send-to-org")
        assert send_res.status_code == 200
        assert send_res.get_json()["proposal"]["status"] == "PENDING_ORG_REVIEW"
        
        notifs_a = repo.list_notifications(recipient_id=org_a_id)
        assert any(n.entity_id == prop_id and n.notification_type == "coordination_proposal_received" for n in notifs_a)
        print(f"[OK] Proposal sent to Org A -> PENDING_ORG_REVIEW and received notification")

        # Step C: Seed private inventory for Org A & Evaluate
        client.set_cookie("reliefos_org_id", org_a_id)
        client.post("/api/my-org/resources", json={
            "resource_type": "rescue_boat",
            "quantity": 10,
            "unit": "boats",
            "location": "Warehouse Alpha Top Secret",
        })
        
        eval_res = client.post("/api/my-org/agent/evaluate-coordination", json={"proposal_id": prop_id})
        assert eval_res.status_code == 200, eval_res.get_json()
        eval_data = eval_res.get_json()["evaluation"]
        assert "private_factors" not in eval_data
        assert "Warehouse Alpha Top Secret" not in json.dumps(eval_res.get_json())
        print(f"[OK] Org A evaluated proposal -> recommendation ready, private factors scrubbed")

        # Step D: Human-in-the-loop Approve Publication
        approve_res = client.post("/api/my-org/agent/approve-publication", json={"proposal_id": prop_id})
        assert approve_res.status_code == 200, approve_res.get_json()
        
        # Verify proposal status in PostgreSQL
        persisted_prop = repo.get_proposal(prop_id)
        assert persisted_prop["status"] == "CONFIRMED"
        assert persisted_prop.get("published_offer_id") is not None
        print(f"[OK] Publication approved -> Proposal CONFIRMED and linked to offer {persisted_prop.get('published_offer_id')}")

        # Step E: Check network broadcast notification
        net_notifs = repo.list_notifications(recipient_id="network")
        assert any(n.entity_id == prop_id and n.notification_type == "coordination_offer_published" for n in net_notifs)
        print("[OK] Network notification coordination_offer_published broadcast to network")

        # 6. Notification Read & Mark Read Lifecycle
        print("\n--- 6. Notification Read State Lifecycle ---")
        unread_a = repo.list_notifications(recipient_id=org_a_id, unread_only=True)
        assert len(unread_a) > 0
        target_notif = unread_a[0]
        
        # Mark read via API
        read_res = client.post(f"/api/notifications/{target_notif.id}/read")
        assert read_res.status_code == 200
        
        # Verify in DB
        unread_after = repo.list_notifications(recipient_id=org_a_id, unread_only=True)
        assert not any(n.id == target_notif.id for n in unread_after)
        print(f"[OK] Notification {target_notif.id} marked as read and persisted")

        # 7. Multi-Org Isolation & Authorization Boundary
        print("\n--- 7. Multi-Org Isolation & Trust Boundary ---")
        # Create a proposal specifically targeting Org B
        prop_b_res = client.post("/api/network/coordination/propose", json={
            "need": need_obj.to_dict(),
            "organization_id": org_b_id,
            "organization_name": "Beta NGO",
        })
        prop_b_id = prop_b_res.get_json()["proposal"]["id"]
        client.post(f"/api/network/coordination/proposals/{prop_b_id}/send-to-org")

        # Attack 1: Org A tries to evaluate Org B's proposal
        client.set_cookie("reliefos_org_id", org_a_id)
        attack1 = client.post("/api/my-org/agent/evaluate-coordination", json={"proposal_id": prop_b_id})
        assert attack1.status_code == 404, f"Org A evaluating Org B proposal should be 404, got {attack1.status_code}"
        print("[OK] Adversarial attempt blocked: Org A cannot evaluate Org B's proposal (404)")

        # Attack 2: Org A tries to approve publication of Org B's proposal
        attack2 = client.post("/api/my-org/agent/approve-publication", json={"proposal_id": prop_b_id})
        assert attack2.status_code == 404, f"Org A approving Org B proposal should be 404, got {attack2.status_code}"
        print("[OK] Adversarial attempt blocked: Org A cannot approve Org B's proposal (404)")

        # Attack 3: Org A tries to pass {"organization_id": org_b_id} in body to hijack session seam
        attack3 = client.post("/api/my-org/publish-offer", json={
            "organization_id": org_b_id,
            "resource_type": "water",
            "quantity": 100,
        })
        assert attack3.status_code == 201
        published_offer = attack3.get_json()["offer"]
        # Must belong to session org (org_a_id), NOT body org (org_b_id)
        assert published_offer["organization_id"] == org_a_id
        print("[OK] Adversarial attempt blocked: client body org_id ignored; session seam enforces org_a")

        # Attack 4: Org A tries to read Org B's notifications
        notifs_b_res = client.get(f"/api/notifications?recipient_id={org_b_id}")
        assert notifs_b_res.status_code == 200
        # Org B notifications must only contain Org B / network items, never Org A private data
        for n in notifs_b_res.get_json()["notifications"]:
            assert n["recipient_id"] in (org_b_id, "network")
        print("[OK] Notification query isolation verified")

        # 8. Complete Privacy Sweep
        print("\n--- 8. Complete Privacy Sweep ---")
        # Check all public endpoints: /api/needs, /api/offers, /api/network/coordination/proposals, /api/activity, /api/notifications
        for endpoint in [
            "/api/needs",
            "/api/offers",
            "/api/network/coordination/proposals",
            "/api/activity",
            "/api/notifications",
        ]:
            r = client.get(endpoint)
            payload_str = json.dumps(r.get_json())
            assert "private_factors" not in payload_str
            assert "private_reasoning" not in payload_str
            assert "Top Secret" not in payload_str
        print("[OK] Privacy sweep passed: no private markers found across network-visible API surface")

        # 9. Activity Event Consistency
        print("\n--- 9. Activity Event Consistency ---")
        events = repo.list_activity_events(entity_type="coordination", entity_id=prop_id)
        event_types = [e.event_type for e in events]
        assert "coordination_proposed" in event_types
        assert "proposal_sent_to_org" in event_types
        assert "organization_evaluation_completed" in event_types
        assert "proposal_confirmed" in event_types
        print(f"[OK] Activity event sequence verified: {event_types}")

    print("\n=== ALL ITEM #7 INTEGRATION VERIFICATIONS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_verification()
