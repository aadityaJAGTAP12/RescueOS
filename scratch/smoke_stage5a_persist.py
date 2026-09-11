"""
ReliefOS Smoke Stage 5 — Task 6: Persistence / restart test.

Stage A (server running): create representative synthetic data covering every
persistent class, verify it, then hard-kill the server.

Stage B (after restart): verify all state survived, no private data became
public, AgentEvents remain safe, stale recovery still works, and the
proactive runtime can resume safely.
"""

import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_lib import (  # noqa: E402
    Http, anon, login, load_manifest, update_manifest, record_ids,
    check, finish_stage, kill_server,
)

m = load_manifest()
tag, password = m["tag"], m["password"]
org_a = m["org_alpha"]
users = m["users"]
pid = m["server_pid"]

alpha_op = login(users["alpha_op"]["username"], password)
tok_op = alpha_op["token"]
netop = login(users["netop"]["username"], password)
tok_net = netop["token"]

suffix = uuid.uuid4().hex[:6]

# --- Create representative persistent state -------------------------------
r = Http(tok_op, org_a).post("/api/needs", json={
    "need_type": "medical", "title": f"Restart durability need {suffix}",
    "district_id": "jorhat", "urgency": "high",
})
check(r.status_code == 201, "restart: need created", r.text[:200])
restart_need = r.json()["need"]
record_ids(needs=[restart_need["id"]])

r = Http(tok_op, org_a).post("/api/my-org/publish-offer", json={
    "resource_type": "medical_kit", "quantity": 25, "unit": "kits",
    "district_id": "jorhat",
})
check(r.status_code == 201, "restart: offer created", r.text[:200])
restart_offer = r.json()["offer"]
record_ids(resource_offers=[restart_offer["id"]])

r = Http(tok_op, org_a).post("/api/operations", json={
    "name": f"Restart durability operation {suffix}",
    "operation_type": "distribution", "need_id": restart_need["id"],
    "lead_organization_id": org_a, "district_id": "jorhat",
})
check(r.status_code == 201, "restart: operation created", r.text[:200])
restart_op = r.json()["operation"]
record_ids(operations=[restart_op["id"]])

r = Http(tok_net).post("/api/network/coordination/propose", json={
    "need": restart_need, "organization_id": org_a, "organization_name": "Smoke Alpha NGO",
})
check(r.status_code == 201, "restart: coordination proposal created", r.text[:200])
restart_prop = r.json()["proposal"]
record_ids(coordination_proposals=[restart_prop["id"]])

# (agent events are created by the mutations above — grab one for this need)
r = Http(tok_net).get("/api/agent/events?limit=50")
evs = [e for e in r.json()["events"] if e.get("entity_id") == restart_need["id"]]
restart_event_id = evs[0]["event_id"] if evs else None
check(restart_event_id is not None, "restart: AgentEvent present for need")
record_ids(agent_events=[restart_event_id])

# Proactive finding: run a manual scan and take a finding id if any
r = Http(tok_net).post("/api/agent/proactive/trigger", json={"scope": {"district_id": "jorhat"}})
check(r.status_code == 200, "restart: proactive scan triggered", str(r.status_code))
restart_scan = r.json()["scan"]
r = Http(tok_net).get(f"/api/agent/proactive/findings?scan_id={restart_scan['id']}&limit=10")
restart_finding_id = (r.json()["findings"][0]["id"] if r.json()["findings"] else None)
record_ids(proactive_scans=[restart_scan["id"]])

# Private inventory (file-backed) — add a marker resource
r = Http(tok_op, org_a).post("/api/my-org/resources", json={
    "resource_type": "generator", "quantity": 2, "unit": "units",
    "location": f"PRIVATE-RESTART-MARKER-{suffix}",
})
check(r.status_code == 201, "restart: private resource created", r.text[:200])
restart_private = r.json()["resource"]
record_ids(private_resources=[restart_private["id"]])

# Audit event marker
r = Http(tok_net).get("/api/audit/logs?limit=20")
check(r.status_code == 200, "restart: audit logs readable pre-kill", str(r.status_code))
audit_before = [e["id"] for e in r.json()["logs"][:10]]
record_ids(audit_logs=audit_before)

update_manifest(restart={
    "need_id": restart_need["id"], "offer_id": restart_offer["id"],
    "op_id": restart_op["id"], "proposal_id": restart_prop["id"],
    "event_id": restart_event_id, "scan_id": restart_scan["id"],
    "finding_id": restart_finding_id,
    "private_resource_id": restart_private["id"],
    "private_marker": f"PRIVATE-RESTART-MARKER-{suffix}",
    "audit_before": audit_before,
})

# --- Plant a stale CLAIMED event BEFORE the kill ----------------------------
# Boot 2's one-shot stale recovery must requeue it and log the recovery —
# this proves the startup recovery path actually runs on restart.
from datetime import datetime, timezone  # noqa: E402
from agent.data.models import AgentEvent, AgentEventType, EventStatus  # noqa: E402
from agent.data.schema import agent_events as ae_table  # noqa: E402
from sqlalchemy import update as sa_update  # noqa: E402

repo = None
os.environ.pop("RELIEFOS_MEMORY", None)
from dotenv import load_dotenv  # noqa: E402
load_dotenv()
from agent.data.repository import get_repository  # noqa: E402
repo = get_repository()
planted = AgentEvent(
    event_id=f"evt_planted_stale_{suffix}",
    event_type=AgentEventType.NEED_CREATED.value,
    status=EventStatus.CLAIMED.value,
    created_at=datetime.now(timezone.utc).isoformat(),
)
repo.append_agent_event(planted)
record_ids(agent_events=[planted.event_id])
with repo._engine.begin() as conn:
    conn.execute(sa_update(ae_table).where(ae_table.c.id == planted.event_id).values(
        claimed_at=datetime(2020, 1, 1, tzinfo=timezone.utc)))
update_manifest(planted_stale_event_id=planted.event_id)
print(f"planted stale CLAIMED event {planted.event_id} before kill")
print("Stage 5A complete — killing server (hard kill / crash scenario)")

# --- Hard kill the production server ---------------------------------------
kill_server(pid)
print("server killed; stage 5A done (restart with stage5b)")
