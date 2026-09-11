"""
ReliefOS Event Router & In-Process Dispatcher — Phase 2A Runtime Architecture

Provides deterministic, typed routing of machine-facing AgentEvents to
NetworkMainAgent and NGOMainAgent, and manages persistent outbox dispatch with:
- Deterministic specialist domain selection (no LLM in control loop)
- Error isolation (worker failures captured as data gaps, no fake findings)
- Idempotency tracking (safe duplicate event rejection)
- Strict privacy preservation (Network never reads NGO private context)
- Zero autonomous writes (HITL safety guarantee)
- Replay & observability support
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from agent.agents.base import AgentFinding, FindingProvenance, FindingSeverity
from agent.agents.events import AgentEvent, AgentEventType, EventStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background stale-claim recovery loop (production hardening)
# ---------------------------------------------------------------------------

_recovery_thread: Optional[threading.Thread] = None
_recovery_stop = threading.Event()


def start_stale_recovery_loop(
    interval_seconds: int = 120,
    stale_threshold_seconds: int = 300,
) -> Optional[threading.Thread]:
    """
    Start a daemon thread that periodically re-queues events stuck in
    CLAIMED/PROCESSING (e.g. after a worker crash). Runs in-process; a future
    external worker can replace it by calling recover_stale_events itself.
    """
    global _recovery_thread
    if _recovery_thread is not None and _recovery_thread.is_alive():
        return _recovery_thread

    def _loop():
        while not _recovery_stop.is_set():
            try:
                dispatcher = get_event_dispatcher()
                recovered = dispatcher.recover_stale_events(
                    stale_threshold_seconds=stale_threshold_seconds,
                )
                if recovered:
                    logger.warning(
                        "Stale event recovery requeued %d event(s)", recovered
                    )
            except Exception as e:
                logger.error("Stale event recovery loop error: %s", e)
            _recovery_stop.wait(timeout=max(5, int(interval_seconds)))

    _recovery_stop.clear()
    _recovery_thread = threading.Thread(
        target=_loop,
        name="reliefos-event-recovery",
        daemon=True,
    )
    _recovery_thread.start()
    logger.info(
        "Stale event recovery loop started (interval=%ds, threshold=%ds)",
        interval_seconds,
        stale_threshold_seconds,
    )
    return _recovery_thread


def stop_stale_recovery_loop(timeout: float = 5.0) -> None:
    """Stop the background recovery loop cleanly."""
    global _recovery_thread
    _recovery_stop.set()
    if _recovery_thread is not None:
        _recovery_thread.join(timeout=timeout)
        _recovery_thread = None


# ---------------------------------------------------------------------------
# Background outbox worker loop (production hardening)
# ---------------------------------------------------------------------------

_worker_thread: Optional[threading.Thread] = None
_worker_stop = threading.Event()


def start_event_worker(
    poll_seconds: int = 5,
    batch_size: int = 10,
    repo=None,
) -> Optional[threading.Thread]:
    """
    Start a daemon thread that continuously claims and dispatches pending
    AgentEvents from the persistent outbox.

    Error isolation: dispatch failures are captured per-event by
    EventDispatcher.dispatch_event; loop-level exceptions are logged and the
    loop continues, so a single bad event or transient DB failure cannot kill
    the worker thread.
    """
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return _worker_thread

    def _loop():
        while not _worker_stop.is_set():
            processed = 0
            try:
                dispatcher = get_event_dispatcher()
                results = dispatcher.process_pending_events(
                    repo=repo, limit=max(1, int(batch_size)),
                )
                processed = len(results)
                failures = [r for r in results if isinstance(r, dict) and r.get("status") == "failed"]
                if failures:
                    logger.error(
                        "Event worker: %d/%d dispatched event(s) failed",
                        len(failures), len(results),
                    )
                if processed:
                    logger.info("Event worker processed %d event(s)", processed)
            except Exception as e:
                logger.error("Event worker loop error: %s", e)
            if processed == 0:
                # Idle — wait for the next poll (interruptible for shutdown).
                _worker_stop.wait(timeout=max(1, int(poll_seconds)))

    _worker_stop.clear()
    _worker_thread = threading.Thread(
        target=_loop,
        name="reliefos-event-worker",
        daemon=True,
    )
    _worker_thread.start()
    logger.info(
        "Event worker started (poll=%ss, batch=%s)", poll_seconds, batch_size,
    )
    return _worker_thread


def stop_event_worker(timeout: float = 5.0) -> None:
    """Stop the background outbox worker cleanly."""
    global _worker_thread
    _worker_stop.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=timeout)
        _worker_thread = None


# ---------------------------------------------------------------------------
# Deterministic Routing Table
# ---------------------------------------------------------------------------

NETWORK_EVENT_ROUTING: dict[str, list[str]] = {
    AgentEventType.NEED_CREATED.value: ["logistics", "coordination", "medical"],
    AgentEventType.NEED_STATUS_CHANGED.value: ["logistics", "coordination"],
    AgentEventType.OFFER_CREATED.value: ["logistics", "coordination"],
    AgentEventType.OFFER_STATUS_CHANGED.value: ["logistics", "coordination"],
    AgentEventType.OPERATION_CREATED.value: ["access", "logistics"],
    AgentEventType.OPERATION_STATUS_CHANGED.value: ["access", "logistics"],
    AgentEventType.FLOOD_SNAPSHOT_UPDATED.value: ["situation", "exposure", "evidence"],
    AgentEventType.ROAD_OVERRIDE_APPLIED.value: ["access", "logistics", "medical"],
    AgentEventType.BRIDGE_OVERRIDE_APPLIED.value: ["access", "logistics"],
    AgentEventType.FIELD_REPORT_CREATED.value: ["field", "medical", "evidence"],
    AgentEventType.COORDINATION_PROPOSAL_CREATED.value: ["coordination", "logistics"],
    AgentEventType.COORDINATION_PROPOSAL_UPDATED.value: ["coordination", "logistics"],
}

NGO_EVENT_ROUTING: dict[str, list[str]] = {
    AgentEventType.NEED_CREATED.value: ["inventory", "team", "mission", "logistics"],
    AgentEventType.COORDINATION_PROPOSAL_RECEIVED.value: ["inventory", "team", "mission", "logistics"],
    AgentEventType.OPERATION_CREATED.value: ["mission", "team", "inventory"],
    AgentEventType.OPERATION_STATUS_CHANGED.value: ["mission", "team"],
    AgentEventType.ROAD_OVERRIDE_APPLIED.value: ["logistics", "field"],
    AgentEventType.BRIDGE_OVERRIDE_APPLIED.value: ["logistics"],
    AgentEventType.FIELD_REPORT_CREATED.value: ["field"],
}


class EventRouter:
    """
    Deterministic domain router. Maps AgentEvents to the appropriate specialist agents.
    """

    @staticmethod
    def route_network_event(event: AgentEvent) -> list[str]:
        """Return list of network specialist names that should process this event."""
        event_type = event.event_type if isinstance(event.event_type, str) else event.event_type.value
        return NETWORK_EVENT_ROUTING.get(event_type, ["situation", "evidence"])

    @staticmethod
    def route_ngo_event(event: AgentEvent) -> list[str]:
        """Return list of NGO specialist names that should process this event."""
        event_type = event.event_type if isinstance(event.event_type, str) else event.event_type.value
        return NGO_EVENT_ROUTING.get(event_type, ["inventory", "team"])


# ---------------------------------------------------------------------------
# In-Process Synchronous Event Dispatcher
# ---------------------------------------------------------------------------

class EventDispatcher:
    """
    Synchronous in-process event dispatcher with persistent outbox integration.
    
    Provides the execution seam that future asynchronous workers (Celery/queues)
    will call.
    """

    def __init__(self):
        self._processed_events: dict[str, float] = {}  # event_id -> timestamp
        self._max_history = 1000

    def is_duplicate(self, event_id: str) -> bool:
        """Check if an event has already been processed recently."""
        return event_id in self._processed_events

    def record_processed(self, event_id: str) -> None:
        """Record an event as processed for idempotency tracking."""
        if len(self._processed_events) >= self._max_history:
            # Evict oldest 20%
            sorted_items = sorted(self._processed_events.items(), key=lambda x: x[1])
            for k, _ in sorted_items[:200]:
                self._processed_events.pop(k, None)
        self._processed_events[event_id] = time.time()

    def dispatch_event(
        self,
        event: AgentEvent,
        repo=None,
        force_replay: bool = False,
    ) -> dict[str, Any]:
        """
        Unified dispatch entry point for both Network and NGO events.
        Persists lifecycle state transitions and records execution provenance.
        """
        if repo is None:
            from agent.data.repository import get_repository
            repo = get_repository()

        # Check idempotency
        if not force_replay and (self.is_duplicate(event.event_id) or event.status == EventStatus.PROCESSED.value):
            return {
                "status": "skipped_duplicate",
                "event_id": event.event_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "findings": [],
                "data_gaps": [],
            }

        # Mark PROCESSING in repository
        if hasattr(repo, "update_agent_event_status"):
            try:
                repo.update_agent_event_status(event.event_id, status=EventStatus.PROCESSING.value)
            except Exception:
                pass

        t_start = time.time()
        try:
            # Route to NGO agent if organization_id is bound, else NetworkMainAgent
            if event.organization_id:
                result = self.dispatch_ngo_event(event, org_id=event.organization_id, repo=repo)
            else:
                result = self.dispatch_network_event(event, repo=repo)

            result["status"] = "success"
            result["dispatched_at"] = datetime.now(timezone.utc).isoformat()
            result["is_replay"] = force_replay

            # Update status to PROCESSED
            if hasattr(repo, "update_agent_event_status"):
                try:
                    repo.update_agent_event_status(
                        event_id=event.event_id,
                        status=EventStatus.PROCESSED.value,
                        processed_at=datetime.now(timezone.utc),
                        execution_result=result,
                    )
                except Exception:
                    pass

            self.record_processed(event.event_id)
            return result

        except Exception as e:
            logger.error(f"Event dispatch failed for {event.event_id}: {e}", exc_info=True)
            error_result = {
                "status": "failed",
                "event_id": event.event_id,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "findings": [],
                "data_gaps": [{"item": "Dispatch failure", "detail": str(e)}],
            }
            if hasattr(repo, "update_agent_event_status"):
                try:
                    repo.update_agent_event_status(
                        event_id=event.event_id,
                        status=EventStatus.FAILED.value,
                        processed_at=datetime.now(timezone.utc),
                        error_detail=str(e),
                        execution_result=error_result,
                    )
                except Exception:
                    pass
            return error_result

    def process_pending_events(self, repo=None, limit: int = 10) -> list[dict[str, Any]]:
        """
        Claim and dispatch pending events from the repository outbox.
        """
        if repo is None:
            from agent.data.repository import get_repository
            repo = get_repository()

        if not hasattr(repo, "claim_pending_agent_events"):
            return []

        claimed_events = repo.claim_pending_agent_events(limit=limit)
        results = []
        for event in claimed_events:
            res = self.dispatch_event(event, repo=repo)
            results.append(res)
        return results

    def recover_stale_events(
        self,
        repo=None,
        stale_threshold_seconds: int = 300,
    ) -> int:
        """
        Recover events stuck in CLAIMED or PROCESSING due to server crashes or worker timeouts.
        Resets retryable events to PENDING or marks exhausted events as FAILED.
        """
        if repo is None:
            from agent.data.repository import get_repository
            repo = get_repository()

        if hasattr(repo, "recover_stale_agent_events"):
            recovered = repo.recover_stale_agent_events(stale_threshold_seconds=stale_threshold_seconds)
            count = len(recovered) if isinstance(recovered, list) else int(recovered)
            if count > 0:
                logger.warning(f"Recovered {count} stale agent events from outbox")
            return count
        return 0

    def replay_event(self, event_id: str, repo=None) -> dict[str, Any]:
        """
        Replay a previously recorded event in read-only advisory mode for observability.
        """
        if repo is None:
            from agent.data.repository import get_repository
            repo = get_repository()

        if hasattr(repo, "get_agent_event"):
            event = repo.get_agent_event(event_id)
            if not event:
                return {
                    "status": "not_found",
                    "event_id": event_id,
                    "error": f"Event {event_id} not found in repository",
                }
            return self.dispatch_event(event, repo=repo, force_replay=True)

        return {"status": "error", "error": "Repository does not support get_agent_event"}

    def dispatch_network_event(
        self,
        event: AgentEvent,
        repo=None,
        force_replay: bool = False,
    ) -> dict[str, Any]:
        """
        Synchronously dispatch an event to the NetworkMainAgent.
        """
        if not force_replay and self.is_duplicate(event.event_id):
            return {
                "status": "skipped_duplicate",
                "event_id": event.event_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "findings": [],
                "data_gaps": [],
            }
        from agent.agents.network_main_agent import NetworkMainAgent
        agent = NetworkMainAgent()
        result = agent.handle_event(event, repo=repo)
        self.record_processed(event.event_id)
        return result

    def dispatch_ngo_event(
        self,
        event: AgentEvent,
        org_id: str,
        private_ctx=None,
        shared_ctx=None,
        repo=None,
        force_replay: bool = False,
    ) -> dict[str, Any]:
        """
        Synchronously dispatch an event to an NGOMainAgent.
        """
        if not force_replay and self.is_duplicate(event.event_id):
            return {
                "status": "skipped_duplicate",
                "event_id": event.event_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "findings": [],
                "data_gaps": [],
            }
        from agent.agents.ngo_main_agent import (
            NGOMainAgent,
            PrivateOrganizationContext,
            SharedNetworkContext,
        )

        if private_ctx is None:
            from agent.org_workspace import list_missions, list_resources, list_teams
            private_ctx = PrivateOrganizationContext(
                org_id=org_id,
                resources=list_resources(org_id),
                teams=list_teams(org_id),
                missions=list_missions(org_id),
            )

        if shared_ctx is None:
            if repo is None:
                from agent.data.repository import get_repository
                repo = get_repository()

            needs = repo.list_needs(status="OPEN") if hasattr(repo, "list_needs") else []
            ops = repo.list_operations() if hasattr(repo, "list_operations") else []
            offers = repo.list_resource_offers() if hasattr(repo, "list_resource_offers") else []
            overrides = []
            try:
                from agent.overrides import get_all_overrides
                overrides = get_all_overrides()
            except Exception:
                pass

            shared_ctx = SharedNetworkContext(
                open_needs=[n.to_dict() if hasattr(n, "to_dict") else n for n in needs],
                active_operations=[o.to_dict() if hasattr(o, "to_dict") else o for o in ops],
                published_offers=[o.to_dict() if hasattr(o, "to_dict") else o for o in offers],
                relevant_overrides=overrides,
            )

        agent = NGOMainAgent(org_id)
        result = agent.handle_event(event, private_ctx=private_ctx, shared_ctx=shared_ctx)
        self.record_processed(event.event_id)
        return result


# Singleton dispatcher instance
_GLOBAL_DISPATCHER = EventDispatcher()


def get_event_dispatcher() -> EventDispatcher:
    """Return the global in-process event dispatcher."""
    return _GLOBAL_DISPATCHER
