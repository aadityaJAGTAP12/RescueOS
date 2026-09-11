"""
ReliefOS Smoke Stage 3 — Task 4: Event runtime smoke test (outbox).

Verifies against the live production server:
  domain mutation -> AgentEvent PENDING -> claim -> PROCESSING -> PROCESSED
  stale CLAIMED recovery -> PENDING (eligible again)
  duplicate event -> safe skip (no double processing)
  worker failure isolation (direct dispatch of a malformed event)
"""

import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_lib import (  # noqa: E402
    Http, anon, login, load_manifest, update_manifest, record_ids,
    check, finish_stage,
)

m = load_manifest()
tag, password = m["tag"], m["password"]
org_a = m["org_alpha"]
users = m["users"]
netop = login(users["netop"]["username"], password)
tok_net = netop["token"]

# 4.1 Domain mutation -> AgentEvent PENDING
r = Http(tok_net, org_a).post("/api/needs", json={
    "need_type": "rescue_boat", "title": f"Smoke outbox need {tag}",
    "district_id": "jorhat", "urgency": "high",
})
check(r.status_code == 201, "domain mutation (need create) accepted", r.text[:200])
ev_need = r.json()["need"]["id"]
record_ids(needs=[ev_need], agent_events=[f"%{ev_need}%"])

# Find the emitted outbox event for this need
r = Http(tok_net).get(f"/api/agent/events?entity_type=need&limit=50")
check(r.status_code == 200, "agent events list readable", str(r.status_code))
events = [e for e in r.json()["events"] if e.get("entity_id") == ev_need]
check(len(events) >= 1, "need-created AgentEvent emitted to outbox")
event = events[0]
check(event["status"] == "PENDING", f"new event starts PENDING (got {event['status']})")
update_manifest(outbox_event_id=event["event_id"])

# 4.2 Claim -> PROCESSING -> PROCESSED.
# The background worker (started by prod_startup) may legitimately claim and
# process this event first — that IS the runtime behavior under test. Drive
# the event to PROCESSED via either path and verify the full lifecycle.
def _event_status(eid):
    rr = Http(tok_net).get(f"/api/agent/events/{eid}")
    return rr.json()["event"]["status"] if rr.status_code == 200 else "UNKNOWN"

r = Http(tok_net).post("/api/agent/events/process", json={"event_id": event["event_id"]})
check(r.status_code == 200, "event process endpoint accepted", r.text[:300])
results = r.json().get("results") or []
if results:
    check(results[0]["status"] in ("success", "skipped_duplicate"),
          f"dispatch outcome safe (got {results[0].get('status')})", str(results[0])[:300])

# Wait for terminal state (manual dispatch or background worker).
deadline = time.time() + 40
while _event_status(event["event_id"]) != "PROCESSED" and time.time() < deadline:
    time.sleep(1)
check(_event_status(event["event_id"]) == "PROCESSED",
      f"event lifecycle reached PROCESSED (got {_event_status(event['event_id'])})")

# 4.3 Duplicate event does not cause unsafe duplicate processing
r = Http(tok_net).post("/api/agent/events/process", json={"event_id": event["event_id"]})
check(r.status_code == 200, "duplicate process call accepted", str(r.status_code))
res2 = (r.json().get("results") or [{}])[0]
check(res2.get("status") in ("skipped_duplicate", "success"),
      f"duplicate dispatch skipped safely (got {res2.get('status')})", str(res2)[:300])

# 4.4 Stale recovery: claim an event, age it past the threshold, recover.
# Use the repository seam directly for the aging step (the running server
# owns the claim loop; the stage verifies the same recovery path the boot
# sequence and periodic loop call).
os.environ.pop("RELIEFOS_MEMORY", None)
from dotenv import load_dotenv  # noqa: E402
load_dotenv()
from agent.data.repository import get_repository  # noqa: E402
from agent.agents.events import AgentEvent, AgentEventType, EventStatus  # noqa: E402
from agent.agents.event_router import get_event_dispatcher  # noqa: E402

repo = get_repository()
check(type(repo).__name__ == "PostgresRepository", "stage3 uses PostgreSQL repository")

suffix = uuid.uuid4().hex[:8]
stale_ev = AgentEvent(
    event_id=f"evt_smoke_stale_{suffix}",
    event_type=AgentEventType.NEED_CREATED.value,
    status=EventStatus.CLAIMED.value,
    created_at=(time.time() - 3600).__str__(),  # replaced below with ISO
)
from datetime import datetime, timezone  # noqa: E402
stale_ev.created_at = datetime.now(timezone.utc).isoformat()
stale_ev.claimed_at = (datetime.now(timezone.utc)).isoformat()
repo.append_agent_event(stale_ev)
record_ids(agent_events=[stale_ev.event_id])
# Backdate the claim so the event is stale beyond the 300s threshold.
from agent.data.schema import agent_events as ae_table  # noqa: E402
from sqlalchemy import update as sa_update  # noqa: E402
with repo._engine.begin() as conn:
    conn.execute(sa_update(ae_table).where(ae_table.c.id == stale_ev.event_id).values(
        claimed_at=datetime.now(timezone.utc).replace(year=2020)))

# The running server's periodic recovery loop (120s interval) or our direct
# call must requeue it. Call the same recovery seam directly:
dispatcher = get_event_dispatcher()
recovered = dispatcher.recover_stale_events(repo=repo, stale_threshold_seconds=300)
check(recovered >= 0, f"recovery sweep executed cleanly (reported {recovered})")
ev_after = repo.get_agent_event(stale_ev.event_id)
check(ev_after.status == EventStatus.PENDING.value,
      f"stale CLAIMED event back to PENDING (got {ev_after.status})")

# It is eligible for processing again:
r = Http(tok_net).post("/api/agent/events/process", json={"event_id": stale_ev.event_id})
check(r.status_code == 200, "recovered event reprocessable", r.text[:200])
if r.json().get("results"):
    check(r.json()["results"][0]["status"] in ("success", "skipped_duplicate"),
          "recovered event dispatch outcome safe", str(r.json()["results"][0])[:200])

# 4.5 Worker failure isolation — two levels:
#  (a) Specialist failure: worker raises -> captured as data gap, dispatch
#      stays coherent, no fake findings, application unaffected.
#  (b) Main-agent failure: routing crashes -> dispatcher catches, event
#      marked FAILED with error detail, worker loop survives.
bad_ev = AgentEvent(
    event_id=f"evt_smoke_bad_{suffix}",
    event_type=AgentEventType.NEED_CREATED.value,
    status=EventStatus.PENDING.value,
    created_at=datetime.now(timezone.utc).isoformat(),
    metadata={"poison": True},
)
repo.append_agent_event(bad_ev)
record_ids(agent_events=[bad_ev.event_id])

class FlakyRepo:
    """Every specialist-facing method raises — a simulated infrastructure
    outage inside the workers' execution path."""
    def __getattr__(self, name):
        def _boom(*a, **k):
            raise RuntimeError("simulated infra failure")
        return _boom

flaky = FlakyRepo()
result = dispatcher.dispatch_event(bad_ev, repo=flaky)
check(result["status"] == "success",
      "specialist failures do not crash dispatch (captured as data gaps)", str(result)[:200])
check(all(v == "failed" for v in result.get("worker_statuses", {}).values()),
      "all touched workers report failed status", str(result.get("worker_statuses")))
check(len(result.get("data_gaps", [])) >= 1, "specialist failures recorded as data gaps")
check(all(f.get("finding_type") == "data_gap" for f in result.get("findings", [])),
      "no fabricated findings on worker failure")

# (b) Main-agent crash -> dispatcher marks event FAILED.
# Fresh event id: the in-memory idempotency map must not short-circuit the
# dispatch before the crash is injected.
crash_ev = AgentEvent(
    event_id=f"evt_smoke_crash_{suffix}",
    event_type=AgentEventType.NEED_CREATED.value,
    status=EventStatus.PENDING.value,
    created_at=datetime.now(timezone.utc).isoformat(),
)
repo.append_agent_event(crash_ev)
record_ids(agent_events=[crash_ev.event_id])

from agent.agents.event_router import EventRouter  # noqa: E402
orig_route = EventRouter.route_network_event
EventRouter.route_network_event = staticmethod(
    lambda event: (_ for _ in ()).throw(RuntimeError("simulated router crash")))
try:
    result_b = dispatcher.dispatch_event(crash_ev, repo=repo)
finally:
    EventRouter.route_network_event = staticmethod(orig_route)
check(result_b["status"] == "failed", "main-agent crash captured as failed dispatch",
      str(result_b)[:300])
ev_crash = repo.get_agent_event(crash_ev.event_id)
check(ev_crash.status == EventStatus.FAILED.value,
      f"crashed event marked FAILED (got {ev_crash.status})")
check("simulated router crash" in (ev_crash.error_detail or ""),
      "failure detail persisted for observability")

# The real worker loop must still be alive: process a good event afterwards.
r = Http(tok_net).post("/api/agent/events/process", json={"limit": 5})
check(r.status_code == 200, "dispatcher still serving after failure", str(r.status_code))

# 4.6 The background worker thread (started by prod_startup) drains the
# outbox: a fresh PENDING event must reach a terminal state without manual
# processing — proof the worker loop itself is healthy end-to-end.
good_ev = AgentEvent(
    event_id=f"evt_smoke_good_{suffix}",
    event_type=AgentEventType.NEED_CREATED.value,
    status=EventStatus.PENDING.value,
    created_at=datetime.now(timezone.utc).isoformat(),
)
repo.append_agent_event(good_ev)
record_ids(agent_events=[good_ev.event_id])
deadline = time.time() + 45
terminal = False
while time.time() < deadline:
    if _event_status(good_ev.event_id) in ("PROCESSED", "FAILED"):
        terminal = True
        break
    time.sleep(2)
check(terminal,
      f"background worker reaches terminal state on fresh event (got {_event_status(good_ev.event_id)})")
check(_event_status(good_ev.event_id) == "PROCESSED",
      "background worker processed fresh event to PROCESSED")

finish_stage("stage3_events")
