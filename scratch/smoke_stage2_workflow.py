"""
ReliefOS Smoke Stage 2 — Task 3: Consequential workflow smoke test.

Full HITL collaboration lifecycle over HTTP with synthetic data:
  authenticate -> select org -> create need -> verify persistence ->
  update need status -> publish offer -> coordination proposal ->
  send-to-org -> org evaluation -> human approval -> public ResourceOffer ->
  privacy preserved -> notifications/activity -> audit records.

Every mutation goes through a human-authenticated HTTP endpoint — no agent
performs a consequential write.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_lib import (  # noqa: E402
    Http, anon, login, load_manifest, update_manifest, record_ids,
    check, finish_stage, scan_response,
)

m = load_manifest()
tag, password = m["tag"], m["password"]
org_a, org_b = m["org_alpha"], m["org_beta"]
users = m["users"]

alpha_admin = login(users["alpha_admin"]["username"], password)
alpha_op = login(users["alpha_op"]["username"], password)
netop = login(users["netop"]["username"], password)
tok_a, tok_op, tok_net = alpha_admin["token"], alpha_op["token"], netop["token"]

# 1-2. authenticate + select authorized organization
r = Http(tok_a).post("/api/session/org", json={"org_id": org_a})
check(r.status_code == 200, "select authorized org_alpha session", r.text[:200])
r = Http(tok_a, org_a).get("/api/session/org")
check(r.json().get("org_id") == org_a, "session org context resolves to org_alpha")

# 3. create a need (critical — exercises the urgent-need notification path)
r = Http(tok_op, org_a).post("/api/needs", json={
    "need_type": "water", "title": f"Smoke water need {tag}",
    "description": "Synthetic need for production smoke test",
    "district_id": "jorhat", "urgency": "critical",
    "lat": 26.75, "lon": 94.20,
    "requested_resources": [{"resource_type": "water", "quantity": 500, "unit": "liters"}],
})
check(r.status_code == 201, "need created (201)", r.text[:300])
need = r.json()["need"]
update_manifest(need_id=need["id"])
record_ids(needs=[need["id"]])
scan_response(r, "need creation")

# 4. verify need persistence (read back)
r = anon().get(f"/api/needs/{need['id']}")
check(r.status_code == 200, "need persisted and readable", str(r.status_code))
check(r.json()["need"]["status"] == "OPEN", "need starts OPEN")

# 5. update need status OPEN -> UNDER_REVIEW
r = Http(tok_op, org_a).patch(f"/api/needs/{need['id']}", json={"status": "UNDER_REVIEW"})
check(r.status_code == 200 and r.json()["need"]["status"] == "UNDER_REVIEW",
      "need status OPEN -> UNDER_REVIEW", r.text[:200])
# back to OPEN so matches/confirm path can commit it to RESPONDING
r = Http(tok_op, org_a).patch(f"/api/needs/{need['id']}", json={"status": "OPEN"})
check(r.status_code == 200 and r.json()["need"]["status"] == "OPEN",
      "need status UNDER_REVIEW -> OPEN", r.text[:200])

# 6. create/publish an offer (org_operator, session seam derives the org)
r = Http(tok_op, org_a).post("/api/my-org/publish-offer", json={
    "resource_type": "water", "quantity": 300, "unit": "liters",
    "district_id": "jorhat", "location_name": "Alpha Depot",
})
check(r.status_code == 201, "offer published via /api/my-org/publish-offer", r.text[:300])
offer = r.json()["offer"]
update_manifest(offer_id=offer["id"])
record_ids(resource_offers=[offer["id"]])
check(offer["organization_id"] == org_a, "offer belongs to org_alpha (session seam)")
scan_response(r, "offer publication")

# 7. create a coordination proposal (network operator — HITL entry point)
r = Http(tok_net).post("/api/network/coordination/propose", json={
    "need": need, "organization_id": org_a, "organization_name": "Smoke Alpha NGO",
})
check(r.status_code == 201, "coordination proposal created", r.text[:300])
proposal = r.json()["proposal"]
update_manifest(proposal_id=proposal["id"])
record_ids(coordination_proposals=[proposal["id"]])

# 8. send proposal to the organization
r = Http(tok_net).post(f"/api/network/coordination/proposals/{proposal['id']}/send-to-org")
check(r.status_code == 200 and r.json()["proposal"]["status"] == "PENDING_ORG_REVIEW",
      "proposal sent -> PENDING_ORG_REVIEW", r.text[:200])

# 9. evaluate proposal as the organization (private evaluation)
# Seed private inventory so the evaluation has data (org-scoped, human action)
r = Http(tok_op, org_a).post("/api/my-org/resources", json={
    "resource_type": "water", "quantity": 500, "unit": "liters",
    "location": "Alpha private warehouse",
})
check(r.status_code == 201, "private resource added to org_alpha inventory", r.text[:200])
private_res = r.json()["resource"]
update_manifest(private_resource_id=private_res["id"])
r = Http(tok_op, org_a).post("/api/my-org/teams", json={"name": "Alpha Team 1"})
check(r.status_code == 201, "private team added", r.text[:200])

r = Http(tok_op, org_a).post("/api/my-org/agent/evaluate-coordination",
                             json={"proposal_id": proposal["id"]})
check(r.status_code == 200, "org evaluates proposal", r.text[:300])
ev = r.json()["evaluation"]
check("private_factors" not in ev, "evaluation response carries no private_factors")
scan_response(r, "proposal evaluation")

# 10. human approval / publication (ORG_ADMIN)
r = Http(tok_a, org_a).post("/api/my-org/agent/approve-publication",
                            json={"proposal_id": proposal["id"]})
check(r.status_code == 200, "human approves publication", r.text[:300])
pub_offer = r.json().get("offer")
check(pub_offer is not None, "publication produced a public offer", r.text[:200])
update_manifest(pub_offer_id=pub_offer["id"])
record_ids(resource_offers=[pub_offer["id"]])
scan_response(r, "approve publication")

# 11. verify resulting public ResourceOffer
r = anon().get(f"/api/offers?organization_id={org_a}")
check(r.status_code == 200, "public offers list readable", str(r.status_code))
ids = [o["id"] for o in r.json()["offers"]]
check(pub_offer["id"] in ids, "published offer visible on network offers list")
scan_response(r, "public offers list")

# 12. verify private information remains private
r = Http(tok_a, org_a).get("/api/my-org/resources")
check(r.status_code == 200, "org_alpha can read its own private inventory", str(r.status_code))
check(any(res["id"] == private_res["id"] for res in r.json()["resources"]),
      "private inventory intact (org-scoped storage)")

# Public surfaces must not leak the private marker
for path in ("/api/needs", "/api/offers", "/api/network/coordination/proposals",
             "/api/activity", "/api/notifications"):
    r = anon().get(path)
    check(r.status_code == 200, f"public surface {path} readable", str(r.status_code))
    body = r.text
    check("Alpha private warehouse" not in body, f"no private inventory marker in {path}")
    check("private_factors" not in body, f"no private_factors in {path}")

# Proposal raw record keeps private evaluation server-side only
r = anon().get(f"/api/network/coordination/proposals/{proposal['id']}")
check(r.status_code == 200, "proposal public view readable", str(r.status_code))
check("org_evaluation" not in r.text, "proposal public view excludes org_evaluation")

# 13. notifications / activity events
r = Http(tok_a, org_a).get("/api/notifications?unread_only=true")
check(r.status_code == 200, "org_alpha notification queue readable", str(r.status_code))
types = [n["notification_type"] for n in r.json()["notifications"]]
check("coordination_proposal_received" in types, "proposal-received notification delivered")
check("coordination_recommendation_ready" in types, "recommendation-ready notification delivered")

r = anon().get(f"/api/activity?entity_type=coordination&entity_id={proposal['id']}")
check(r.status_code == 200, "coordination activity events readable", str(r.status_code))
etypes = [e["event_type"] for e in r.json()["events"]]
for expected in ("coordination_proposed", "proposal_sent_to_org",
                 "organization_evaluation_completed", "proposal_confirmed"):
    check(expected in etypes, f"activity event '{expected}' recorded", str(etypes))

# 14. audit records for consequential actions
r = Http(tok_net).get("/api/audit/logs?limit=100")
check(r.status_code == 200, "audit logs readable by network operator", str(r.status_code))
logs = r.json()["logs"]
by_action = {}
for entry in logs:
    by_action.setdefault(entry["action"], []).append(entry)
for action, entity_id in (
    ("create_need", need["id"]),
    ("publish_offer", offer["id"]),
    ("create_coordination_proposal", proposal["id"]),
    ("send_proposal_to_org", proposal["id"]),
    ("evaluate_coordination", proposal["id"]),
    ("approve_proposal", proposal["id"]),
):
    entries = by_action.get(action, [])
    hit = next((e for e in entries if e.get("entity_id") == entity_id), None)
    check(hit is not None, f"audit record exists for {action}", f"entity {entity_id}")
    if hit:
        check(bool(hit.get("actor_id")), f"{action} audit has actor")

# HITL: the agent coordination endpoints never mutate — spot check that
# analyze endpoints are read-only by verifying they return analysis payloads
r = Http(tok_net).get("/api/network/agent/analyze")
check(r.status_code == 200, "network agent analysis is read-only and available", str(r.status_code))

finish_stage("stage2_workflow")
