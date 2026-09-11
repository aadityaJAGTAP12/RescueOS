"""
ReliefOS Smoke Stage 1 — Task 2: End-to-end security smoke test.

Exercised against the REAL production server over HTTP:
  Authentication : unauthenticated -> 401; invalid/expired/tampered -> 401;
                   authenticated -> 200.
  Organization isolation (org_alpha vs org_beta):
    - forged reliefos_org_id cookie cannot escape membership
    - body org_id spoofing cannot override the session seam
    - cross-org offers / operations / notifications / proposals /
      private NGO agent state all rejected
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from smoke_lib import (  # noqa: E402
    Http, anon, login, load_manifest, update_manifest, record_ids,
    check, finish_stage, scan_response, ROOT,
)

# .env must be loaded so the expired-token signature matches the server's
# RELIEFOS_SECRET_KEY (python-dotenv does not override pre-set vars).
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(ROOT, ".env"))

m = load_manifest()
tag, password = m["tag"], m["password"]
org_a, org_b = m["org_alpha"], m["org_beta"]
users = m["users"]

# --- Login over real HTTP ---------------------------------------------------
alpha_admin = login(users["alpha_admin"]["username"], password)
alpha_op = login(users["alpha_op"]["username"], password)
beta_admin = login(users["beta_admin"]["username"], password)
netop = login(users["netop"]["username"], password)
check(alpha_admin["user"]["id"] == users["alpha_admin"]["id"], "alpha_admin login identity matches")
check(netop["is_network_operator"] is True, "netop principal is NETWORK_OPERATOR")
check(alpha_admin["memberships"][0]["organization_id"] == org_a, "alpha_admin membership is org_alpha")

tok_a = alpha_admin["token"]
tok_op = alpha_op["token"]
tok_b = beta_admin["token"]
tok_net = netop["token"]

# Wrong password must fail
r = anon().post("/api/auth/login", json={"username": users["alpha_admin"]["username"], "password": "wrong"})
check(r.status_code == 401, "wrong password rejected (401)", r.text[:120])
scan_response(r, "login failure response")

# --- 2.1 Authentication boundary --------------------------------------------
r = anon().get("/api/my-org/summary")
check(r.status_code == 401, "unauthenticated /api/my-org/summary -> 401", str(r.status_code))
r = anon().get("/api/my-org/summary", headers={"Authorization": "Bearer not-a-real-token"})
check(r.status_code == 401, "invalid token -> 401", str(r.status_code))

# Tampered token (flipped signature) — signature verification rejection path.
tampered = alpha_admin["token"][:-6] + "aaaaaa"
r = anon().get("/api/my-org/summary", headers={"Authorization": f"Bearer {tampered}"})
check(r.status_code == 401, "tampered token -> 401", str(r.status_code))

# Expired token: minted with the same secret the server uses (env),
# expiry 60s in the past — expiration verification path.
from agent.auth.service import create_session_token  # noqa: E402
expired_token = create_session_token(
    user_id=users["alpha_admin"]["id"],
    username=users["alpha_admin"]["username"],
    secret_key=os.environ.get("RELIEFOS_SECRET_KEY", ""),
    expires_in_seconds=-60,
)
r = anon().get("/api/my-org/summary", headers={"Authorization": f"Bearer {expired_token}"})
check(r.status_code == 401, "expired token -> 401", str(r.status_code))

r = Http(tok_a, org_a).get("/api/my-org/summary")
check(r.status_code == 200, "authenticated summary -> 200", r.text[:200])
check(r.json().get("org_id") == org_a, "summary resolves org_alpha")
scan_response(r, "my-org summary")

r = Http(tok_a).get("/api/auth/me")
check(r.status_code == 200 and r.json()["authenticated"] is True, "auth/me works with bearer")

# --- 2.2 Organization isolation ----------------------------------------------
# Forged cookie: alpha user sets reliefos_org_id=org_beta
h = Http(tok_a, org_b)
r = h.get("/api/my-org/summary")
check(r.status_code == 200 and r.json().get("org_id") == org_a,
      "forged org cookie cannot escape membership (resolves org_alpha)", r.text[:200])

# Session org selection: alpha cannot select org_beta
r = Http(tok_a).post("/api/session/org", json={"org_id": org_b})
check(r.status_code == 403, "alpha cannot select org_beta session (403)", str(r.status_code))
r = Http(tok_a).post("/api/session/org", json={"org_id": org_a})
check(r.status_code == 200, "alpha can select org_alpha session", str(r.status_code))

# Body org_id spoofing on offer creation
r = Http(tok_op, org_a).post("/api/offers", json={
    "resource_type": "water", "quantity": 10, "unit": "liters",
    "organization_id": org_b,  # spoofed
})
check(r.status_code == 201, "offer creation succeeds", r.text[:200])
spoofed_offer = r.json()["offer"]
check(spoofed_offer["organization_id"] == org_a,
      "body organization_id spoof ignored (server-side seam wins)")
update_manifest(spoofed_offer_id=spoofed_offer["id"])
record_ids(resource_offers=[spoofed_offer["id"]])
scan_response(r, "offer creation")

# Cross-org offer PATCH (alpha operator attacks beta's offer)
# First create an offer that belongs to org_beta
r = Http(tok_b, org_b).post("/api/offers", json={
    "resource_type": "food", "quantity": 5, "unit": "kg"})
check(r.status_code == 201, "org_beta offer creation succeeds", r.text[:200])
beta_offer = r.json()["offer"]
record_ids(resource_offers=[beta_offer["id"]])
r = Http(tok_op, org_a).patch(f"/api/offers/{beta_offer['id']}", json={"status": "WITHDRAWN"})
check(r.status_code == 403, "cross-org offer PATCH -> 403", f"{r.status_code} {r.text[:120]}")

# Cross-org private NGO state
for path in ("/api/my-org/summary", "/api/my-org/resources", "/api/my-org/teams", "/api/my-org/missions"):
    r = Http(tok_b, org_b).get(path)
    check(r.status_code == 200, f"org_beta sees own {path}", str(r.status_code))
    body = r.text
    check(org_a not in body, f"org_beta {path} carries no org_alpha identifiers")

# Beta cannot mark alpha's notification read / read alpha's notifications
r = Http(tok_a, org_a).get("/api/notifications")
check(r.status_code == 200, "alpha reads own notifications", str(r.status_code))
alpha_notifs = r.json()["notifications"]
if alpha_notifs:
    nid = alpha_notifs[0]["id"]
    r = Http(tok_b, org_b).post(f"/api/notifications/{nid}/read")
    check(r.status_code == 403, "cross-org notification mark-read -> 403", str(r.status_code))
r = Http(tok_b, org_b).get(f"/api/notifications?recipient_id={org_a}")
check(r.status_code == 403, "cross-org notification list -> 403", str(r.status_code))

# Cross-org proposal evaluation (beta attacks alpha's proposal)
# netop creates a proposal targeting org_alpha, sends it
r = Http(tok_net).post("/api/network/coordination/propose", json={
    "need": {"id": f"need_sec_{tag}", "need_type": "water", "title": "sec smoke",
             "district_id": "jorhat", "urgency": "high"},
    "organization_id": org_a, "organization_name": "Smoke Alpha NGO",
})
check(r.status_code == 201, "netop coordination proposal created", r.text[:300])
prop = r.json()["proposal"]
update_manifest(sec_proposal_id=prop["id"])
record_ids(coordination_proposals=[prop["id"]])
scan_response(r, "proposal creation")

r = Http(tok_net).post(f"/api/network/coordination/proposals/{prop['id']}/send-to-org")
check(r.status_code == 200, "proposal sent to org_alpha", r.text[:200])

r = Http(tok_b, org_b).post("/api/my-org/agent/evaluate-coordination",
                            json={"proposal_id": prop["id"]})
check(r.status_code == 404, "beta evaluate alpha's proposal -> 404", str(r.status_code))
r = Http(tok_b, org_b).post("/api/my-org/agent/approve-publication",
                            json={"proposal_id": prop["id"]})
check(r.status_code == 404, "beta approve alpha's proposal -> 404", str(r.status_code))

# Forged-cookie + spoofed-body attempt on private state: alpha user with a
# forged org_beta cookie must still see org_alpha's private workspace.
r = Http(tok_a, org_b).get("/api/my-org/resources")
check(r.status_code == 200 and org_b not in r.text,
      "forged cookie cannot redirect private inventory reads to org_beta")

# Audit access for org users must be denied (network operator only).
r = Http(tok_a, org_a).get("/api/audit/logs")
check(r.status_code == 403, "org user cannot read audit logs (403)", str(r.status_code))
r = Http(tok_net).get("/api/audit/logs")
check(r.status_code == 200, "network operator can read audit logs", str(r.status_code))

# Error sanitization spot-check: trigger a 404 and a validation error and
# verify no internals leak.
r = anon().get("/api/needs/need_does_not_exist_zz")
check(r.status_code == 404, "unknown need -> 404", str(r.status_code))
scan_response(r, "404 response")
r = anon().post("/api/auth/login", json={})
check(r.status_code == 400, "empty login body -> 400", str(r.status_code))
scan_response(r, "validation error response")

# Agent runtime endpoints require auth
for path in ("/api/agent/events", "/api/agent/proactive/scans", "/api/agent/proactive/findings"):
    r = anon().get(path)
    check(r.status_code == 401, f"unauthenticated {path} -> 401", str(r.status_code))

finish_stage("stage1_security")
