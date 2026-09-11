"""
Tests for ReliefOS Phase 2A — Persistent Event-Driven Agent Runtime

Validates:
1. AgentEvent outbox persistence and schema in both InMemory and PostgreSQL repositories.
2. Full lifecycle state transitions (PENDING -> CLAIMED -> PROCESSING -> PROCESSED / FAILED / SKIPPED_DUPLICATE).
3. Atomic claiming of pending events.
4. Process restart simulation (Process 1 writes -> process exit -> Process 2 reads & executes).
5. Deterministic specialist routing for Network and NGO event types.
6. Dispatcher execution, failure isolation, and idempotency.
7. Event replay in read-only advisory mode.
8. Human-in-the-loop (HITL) safeguard: zero autonomous writes during dispatch.
9. Privacy boundaries: Network cannot access NGO private context.
10. API endpoints for listing, inspecting, processing, and replaying agent events.
"""

import os
import uuid
import pytest
from datetime import datetime, timezone

from agent.agents.events import (
    AgentEvent,
    AgentEventType,
    EventStatus,
    make_need_created_event,
    make_need_status_changed_event,
    make_offer_created_event,
    make_offer_status_changed_event,
    make_operation_created_event,
    make_operation_status_changed_event,
    make_flood_snapshot_event,
    make_road_override_event,
    make_bridge_override_event,
    make_field_report_event,
    make_coordination_proposal_created_event,
    make_proposal_received_event,
    make_coordination_proposal_updated_event,
)
from agent.agents.event_router import EventRouter, EventDispatcher, NETWORK_EVENT_ROUTING, NGO_EVENT_ROUTING
from agent.data.repository import InMemoryRepository
from agent.data.models import Need, ResourceOffer, Operation


# ---------------------------------------------------------------------------
# 1. AgentEvent Persistence & Model Tests (InMemoryRepository)
# ---------------------------------------------------------------------------

def test_agent_event_creation_and_to_from_dict():
    evt = make_need_created_event(
        need_id="need_123",
        district="sivasagar",
        priority="critical",
        metadata={"urgency": "critical", "need_type": "rescue"},
    )
    assert evt.entity_id == "need_123"
    assert evt.entity_type == "need"
    assert evt.event_type == AgentEventType.NEED_CREATED.value
    assert evt.priority == "critical"
    assert evt.status == EventStatus.PENDING.value

    d = evt.to_dict()
    assert d["entity_id"] == "need_123"
    assert d["status"] == "PENDING"
    assert d["metadata"]["need_type"] == "rescue"

    restored = AgentEvent.from_dict(d)
    assert restored.event_id == evt.event_id
    assert restored.event_type == evt.event_type
    assert restored.status == EventStatus.PENDING.value
    assert restored.metadata == evt.metadata


def test_in_memory_repository_agent_event_crud():
    repo = InMemoryRepository()

    # Append
    evt1 = make_need_created_event("need_a", district="jorhat")
    evt2 = make_offer_created_event("offer_b", org_id="org_redcross", district="jorhat")
    repo.append_agent_event(evt1)
    repo.append_agent_event(evt2)

    # Get
    fetched = repo.get_agent_event(evt1.event_id)
    assert fetched is not None
    assert fetched.event_id == evt1.event_id
    assert fetched.entity_id == "need_a"

    # List
    all_events = repo.list_agent_events()
    assert len(all_events) == 2

    # Filter by entity_type
    need_events = repo.list_agent_events(entity_type="need")
    assert len(need_events) == 1
    assert need_events[0].event_id == evt1.event_id

    # Filter by status
    pending_events = repo.list_agent_events(status=EventStatus.PENDING.value)
    assert len(pending_events) == 2

    # Update status
    updated = repo.update_agent_event_status(
        event_id=evt1.event_id,
        status=EventStatus.PROCESSING.value,
    )
    assert updated is not None
    assert updated.status == EventStatus.PROCESSING.value
    assert repo.get_agent_event(evt1.event_id).status == EventStatus.PROCESSING.value

    # Check pending list reduced
    pending_events = repo.list_agent_events(status=EventStatus.PENDING.value)
    assert len(pending_events) == 1
    assert pending_events[0].event_id == evt2.event_id


def test_atomic_claiming_in_memory():
    repo = InMemoryRepository()
    for i in range(5):
        evt = make_need_created_event(f"need_{i}", district="sivasagar")
        repo.append_agent_event(evt)

    # Claim batch of 3
    batch1 = repo.claim_pending_agent_events(limit=3)
    assert len(batch1) == 3
    for b in batch1:
        assert b.status == EventStatus.CLAIMED.value

    # Claim next batch
    batch2 = repo.claim_pending_agent_events(limit=3)
    assert len(batch2) == 2
    for b in batch2:
        assert b.status == EventStatus.CLAIMED.value

    # No more pending
    batch3 = repo.claim_pending_agent_events(limit=3)
    assert len(batch3) == 0


# ---------------------------------------------------------------------------
# 2. Deterministic Routing Tests
# ---------------------------------------------------------------------------

def test_deterministic_network_routing():
    router = EventRouter()

    # Need created -> logistics, coordination, medical
    evt_need = make_need_created_event("need_1")
    specialists = router.route_network_event(evt_need)
    assert specialists == ["logistics", "coordination", "medical"]

    # Flood updated -> situation, exposure, evidence
    evt_flood = make_flood_snapshot_event("snap_1", "sivasagar")
    specialists = router.route_network_event(evt_flood)
    assert specialists == ["situation", "exposure", "evidence"]

    # Road override -> access, logistics, medical
    evt_road = make_road_override_event("ov_1", "NH-37")
    specialists = router.route_network_event(evt_road)
    assert specialists == ["access", "logistics", "medical"]

    # Bridge override -> access, logistics
    evt_bridge = make_bridge_override_event("ov_2", "Dikhow Bridge")
    specialists = router.route_network_event(evt_bridge)
    assert specialists == ["access", "logistics"]

    # Field report -> field, medical, evidence
    evt_field = make_field_report_event("rep_1")
    specialists = router.route_network_event(evt_field)
    assert specialists == ["field", "medical", "evidence"]


def test_deterministic_ngo_routing():
    router = EventRouter()

    # Proposal received -> inventory, team, mission, logistics
    evt_prop = make_proposal_received_event("prop_1", org_id="org_redcross")
    specialists = router.route_ngo_event(evt_prop)
    assert specialists == ["inventory", "team", "mission", "logistics"]

    # Operation created -> mission, team, inventory
    evt_op = make_operation_created_event("op_1", org_id="org_redcross")
    specialists = router.route_ngo_event(evt_op)
    assert specialists == ["mission", "team", "inventory"]


# ---------------------------------------------------------------------------
# 3. Process Restart & Repository Reset Simulation
# ---------------------------------------------------------------------------

def test_process_restart_simulation():
    """
    Simulates:
    1. Process 1 (Producer) creates operational entities and emits AgentEvents into outbox.
    2. Process 1 terminates.
    3. Process 2 (Consumer/Worker) spins up, claims pending events from outbox,
       executes Main Agent delegation, and marks them PROCESSED with recorded findings.
    """
    # Shared storage across processes
    shared_repo = InMemoryRepository()

    # --- PROCESS 1: Emits events on operational change ---
    need = Need(
        id="need_restart_test",
        need_type="medical",
        title="Emergency Insulin Required",
        urgency="critical",
        district_id="sivasagar",
        status="OPEN",
        lat=26.98,
        lon=94.63,
    )
    shared_repo.create_need(need)

    event_1 = make_need_created_event(
        need_id=need.id,
        district=need.district_id,
        priority="critical",
        metadata={"title": need.title, "need_type": need.need_type},
    )
    shared_repo.append_agent_event(event_1)

    # Verify event is PENDING in storage
    assert shared_repo.get_agent_event(event_1.event_id).status == EventStatus.PENDING.value

    # --- SIMULATE PROCESS 1 TERMINATION & PROCESS 2 STARTUP ---
    # Process 2 instantiates a new EventDispatcher with no in-memory cache
    process2_dispatcher = EventDispatcher()

    # Process 2 claims and processes pending events
    claimed = shared_repo.claim_pending_agent_events(limit=10)
    assert len(claimed) == 1
    assert claimed[0].event_id == event_1.event_id
    assert claimed[0].status == EventStatus.CLAIMED.value

    # Process 2 dispatches the claimed event
    result = process2_dispatcher.dispatch_event(claimed[0], repo=shared_repo)

    assert result["status"] == "success"
    assert "findings" in result
    assert result["event_id"] == event_1.event_id

    # Verify final state in persistent repository
    persisted_event = shared_repo.get_agent_event(event_1.event_id)
    assert persisted_event.status == EventStatus.PROCESSED.value
    assert persisted_event.processed_at is not None
    assert persisted_event.execution_result is not None


def test_postgres_process_restart_simulation():
    """
    Explicit PostgreSQL outbox test across independent repository connections.
    """
    from agent.data.postgres_repository import PostgresRepository
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        pytest.skip("DATABASE_URL not set — skipping PostgreSQL restart test")

    # --- PROCESS 1: Connects, writes need and outbox event, then disconnects ---
    repo1 = PostgresRepository(database_url=db_url)
    need_id = f"need_pg_restart_{str(uuid.uuid4())[:8]}"
    need = Need(
        id=need_id,
        need_type="medical",
        title="Postgres Outbox Restart Test",
        urgency="critical",
        district_id="sivasagar",
        status="OPEN",
        lat=26.98,
        lon=94.63,
    )
    repo1.create_need(need)

    event_id = f"evt_pg_restart_{str(uuid.uuid4())[:8]}"
    evt = AgentEvent(
        event_id=event_id,
        event_type=AgentEventType.NEED_CREATED.value,
        entity_type="need",
        entity_id=need_id,
        district="sivasagar",
        priority="critical",
        status=EventStatus.PENDING.value,
    )
    repo1.append_agent_event(evt)
    del repo1  # Terminate Process 1 connection

    # --- PROCESS 2: Independent fresh connection and dispatcher ---
    repo2 = PostgresRepository(database_url=db_url)
    dispatcher2 = EventDispatcher()

    # Claim pending event from PostgreSQL outbox using FOR UPDATE SKIP LOCKED
    claimed = repo2.claim_pending_agent_events(limit=100)
    target = next((e for e in claimed if e.event_id == event_id), None)
    if target is None:
        target = repo2.get_agent_event(event_id)
        if target and target.status == EventStatus.PENDING.value:
            target = repo2.update_agent_event_status(event_id, status=EventStatus.CLAIMED.value)
    assert target is not None
    assert target.status == EventStatus.CLAIMED.value

    # Dispatch claimed event
    res = dispatcher2.dispatch_event(target, repo=repo2)
    assert res["status"] == "success"

    # Verify persisted in PostgreSQL
    final_evt = repo2.get_agent_event(event_id)
    assert final_evt.status == EventStatus.PROCESSED.value
    assert final_evt.processed_at is not None
    assert final_evt.execution_result is not None


# ---------------------------------------------------------------------------
# 4. Outbox Lifecycle, Idempotency & Replay
# ---------------------------------------------------------------------------

def test_event_lifecycle_and_idempotency():
    repo = InMemoryRepository()
    dispatcher = EventDispatcher()

    evt = make_need_created_event("need_lifecycle_test", district="sivasagar")
    repo.append_agent_event(evt)

    # 1. First dispatch -> success & PROCESSED
    res1 = dispatcher.dispatch_event(evt, repo=repo)
    assert res1["status"] == "success"

    persisted = repo.get_agent_event(evt.event_id)
    assert persisted.status == EventStatus.PROCESSED.value

    # 2. Duplicate dispatch attempt -> skipped_duplicate
    res2 = dispatcher.dispatch_event(persisted, repo=repo, force_replay=False)
    assert res2["status"] == "skipped_duplicate"

    # 3. Force replay -> succeeds with is_replay=True
    replay_res = dispatcher.replay_event(evt.event_id, repo=repo)
    assert replay_res["status"] == "success"
    assert replay_res["is_replay"] is True


def test_process_pending_events_batch():
    repo = InMemoryRepository()
    dispatcher = EventDispatcher()

    # Emit 4 events
    for i in range(4):
        evt = make_need_created_event(f"need_batch_{i}", district="sivasagar")
        repo.append_agent_event(evt)

    assert len(repo.list_agent_events(status=EventStatus.PENDING.value)) == 4

    # Process pending in batch
    results = dispatcher.process_pending_events(repo=repo, limit=10)
    assert len(results) == 4
    for r in results:
        assert r["status"] == "success"

    # All events now PROCESSED
    assert len(repo.list_agent_events(status=EventStatus.PENDING.value)) == 0
    assert len(repo.list_agent_events(status=EventStatus.PROCESSED.value)) == 4


# ---------------------------------------------------------------------------
# 5. Failure Isolation & Non-blocking Error Handling
# ---------------------------------------------------------------------------

def test_failure_isolation_on_corrupt_event():
    repo = InMemoryRepository()
    dispatcher = EventDispatcher()

    # Corrupt event with invalid routing
    corrupt_evt = AgentEvent(
        event_id="evt_corrupt",
        event_type="non_existent_type",
        entity_type="unknown",
        entity_id="bad_id",
        status=EventStatus.PENDING.value,
    )
    repo.append_agent_event(corrupt_evt)

    # Normal event
    normal_evt = make_need_created_event("need_ok", district="sivasagar")
    repo.append_agent_event(normal_evt)

    # Process all pending
    results = dispatcher.process_pending_events(repo=repo, limit=10)
    assert len(results) == 2

    # Both were processed without crashing the loop
    persisted_corrupt = repo.get_agent_event("evt_corrupt")
    assert persisted_corrupt.status in (EventStatus.PROCESSED.value, EventStatus.FAILED.value)

    persisted_ok = repo.get_agent_event(normal_evt.event_id)
    assert persisted_ok.status == EventStatus.PROCESSED.value


# ---------------------------------------------------------------------------
# 6. HITL Safety Safeguard (Zero Autonomous Writes)
# ---------------------------------------------------------------------------

def test_hitl_safeguard_zero_domain_writes_during_dispatch():
    """
    Validates that dispatching events generates structured advisory findings
    and execution results, but NEVER creates or mutates Needs, Offers, or
    Operations autonomously.
    """
    repo = InMemoryRepository()
    dispatcher = EventDispatcher()

    need = Need(
        id="need_hitl_check",
        need_type="food_water",
        title="Ration needed",
        urgency="high",
        district_id="sivasagar",
        status="OPEN",
    )
    repo.create_need(need)

    initial_needs_count = len(repo.list_needs())
    initial_offers_count = len(repo.list_resource_offers())
    initial_ops_count = len(repo.list_operations())

    # Dispatch need created event
    evt = make_need_created_event(need.id, district="sivasagar")
    repo.append_agent_event(evt)
    dispatcher.dispatch_event(evt, repo=repo)

    # Assert domain entity counts are strictly unchanged
    assert len(repo.list_needs()) == initial_needs_count
    assert len(repo.list_resource_offers()) == initial_offers_count
    assert len(repo.list_operations()) == initial_ops_count

    # Assert need status is still OPEN (not autonomously changed)
    assert repo.get_need(need.id).status == "OPEN"


# ---------------------------------------------------------------------------
# 7. Privacy Boundary Isolation Tests
# ---------------------------------------------------------------------------

def test_network_event_dispatch_does_not_access_private_ngo_data():
    """
    Network events dispatched to NetworkMainAgent must evaluate public network
    operational state and produce findings without leaking NGO private inventory.
    """
    from agent.org_workspace import add_resource
    repo = InMemoryRepository()
    dispatcher = EventDispatcher()

    # Add private NGO resource
    add_resource("org_secret_ngo", {
        "id": "priv_res_1",
        "resource_type": "boats",
        "quantity": 5,
        "status": "available",
    })

    # Dispatch network need event
    evt = make_need_created_event("need_pub", district="sivasagar")
    repo.append_agent_event(evt)

    result = dispatcher.dispatch_event(evt, repo=repo)
    assert result["status"] == "success"

    # Ensure findings do not reference private NGO resource id
    result_str = str(result)
    assert "priv_res_1" not in result_str
    assert "org_secret_ngo" not in result_str


def test_ngo_event_dispatch_isolated_to_session_org():
    """
    NGO event dispatch routes to NGOMainAgent and evaluates only that organization's context.
    """
    from agent.org_workspace import add_resource
    repo = InMemoryRepository()
    dispatcher = EventDispatcher()

    # Add resources for Org A and Org B
    add_resource("org_a", {"id": "res_a", "resource_type": "medical_kits", "quantity": 10})
    add_resource("org_b", {"id": "res_b", "resource_type": "trucks", "quantity": 2})

    # Dispatch proposal received event for Org A
    evt = make_proposal_received_event("prop_ngo_a", org_id="org_a")
    repo.append_agent_event(evt)

    result = dispatcher.dispatch_event(evt, repo=repo)
    assert result["status"] == "success"

    # Findings should not contain Org B's private resources
    result_str = str(result)
    assert "res_b" not in result_str


# ---------------------------------------------------------------------------
# 8. API Integration Tests for Agent Events
# ---------------------------------------------------------------------------

def test_api_agent_events_endpoints():
    from agent.api import app
    from agent.data.repository import get_repository
    client = app.test_client()
    repo = get_repository()

    # 1. Create a need via API -> should emit AgentEvent outbox entry
    resp = client.post("/api/needs", json={
        "need_type": "rescue",
        "title": "People stranded on roof",
        "district_id": "sivasagar",
        "urgency": "critical",
    })
    assert resp.status_code == 201
    need_id = resp.get_json()["need"]["id"]

    # 2. List agent events via API
    resp = client.get("/api/agent/events?entity_type=need")
    assert resp.status_code == 200
    events = resp.get_json()["events"]
    assert len(events) >= 1
    matched_event = next((e for e in events if e["entity_id"] == need_id), None)
    assert matched_event is not None
    assert matched_event["status"] == "PENDING"
    event_id = matched_event["id"]

    # 3. Get single event
    resp = client.get(f"/api/agent/events/{event_id}")
    assert resp.status_code == 200
    assert resp.get_json()["event"]["id"] == event_id

    # 4. Trigger event processing via API
    resp = client.post("/api/agent/events/process", json={"event_id": event_id})
    assert resp.status_code == 200
    proc_data = resp.get_json()
    assert proc_data["processed_count"] == 1

    # Verify event is now PROCESSED
    resp = client.get(f"/api/agent/events/{event_id}")
    assert resp.status_code == 200
    assert resp.get_json()["event"]["status"] == "PROCESSED"

    # 5. Trigger event replay via API
    resp = client.post(f"/api/agent/events/{event_id}/replay")
    assert resp.status_code == 200
    replay_data = resp.get_json()
    assert replay_data["status"] == "success"
    assert replay_data["is_replay"] is True
