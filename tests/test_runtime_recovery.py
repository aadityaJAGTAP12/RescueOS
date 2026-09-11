"""
ReliefOS Production Hardening — Runtime Reliability & Stale Outbox Recovery Test Suite

Tests event-driven outbox stale claim recovery, retry exhaustion, and dispatcher reliability.
"""

import time
from datetime import datetime, timezone, timedelta
import pytest

from agent.agents.events import AgentEvent, AgentEventType, EventStatus
from agent.agents.event_router import EventDispatcher
from agent.data.repository import InMemoryRepository


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def dispatcher():
    return EventDispatcher()


class TestOutboxStaleClaimRecovery:
    def test_stale_claimed_event_recovery(self, repo, dispatcher):
        # Create an event in CLAIMED state with old timestamp
        past_time = datetime.now(timezone.utc) - timedelta(seconds=600)
        event = AgentEvent(
            event_id="evt_stale_1",
            event_type=AgentEventType.NEED_CREATED.value,
            status=EventStatus.CLAIMED.value,
            retry_count=0,
            max_retries=3,
            created_at=past_time.isoformat(),
        )
        repo.append_agent_event(event)

        # Non-stale event
        recent_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        recent_event = AgentEvent(
            event_id="evt_active_1",
            event_type=AgentEventType.NEED_CREATED.value,
            status=EventStatus.CLAIMED.value,
            retry_count=0,
            max_retries=3,
            created_at=recent_time.isoformat(),
        )
        repo.append_agent_event(recent_event)

        # Run recovery with threshold 300s
        recovered_count = dispatcher.recover_stale_events(repo=repo, stale_threshold_seconds=300)
        assert recovered_count == 1

        # Check state of evt_stale_1 -> should be PENDING with retry_count 1
        stale_reloaded = repo.get_agent_event("evt_stale_1")
        assert stale_reloaded.status == EventStatus.PENDING.value
        assert stale_reloaded.retry_count == 1

        # Check state of evt_active_1 -> should remain CLAIMED
        active_reloaded = repo.get_agent_event("evt_active_1")
        assert active_reloaded.status == EventStatus.CLAIMED.value
        assert active_reloaded.retry_count == 0

    def test_stale_event_retry_exhaustion_marks_failed(self, repo, dispatcher):
        # Create an event that has reached max_retries
        past_time = datetime.now(timezone.utc) - timedelta(seconds=600)
        event = AgentEvent(
            event_id="evt_exhausted_1",
            event_type=AgentEventType.NEED_CREATED.value,
            status=EventStatus.PROCESSING.value,
            retry_count=3,
            max_retries=3,
            created_at=past_time.isoformat(),
        )
        repo.append_agent_event(event)

        recovered_count = dispatcher.recover_stale_events(repo=repo, stale_threshold_seconds=300)
        assert recovered_count == 0  # 0 recovered to pending, event transitioned to FAILED

        reloaded = repo.get_agent_event("evt_exhausted_1")
        assert reloaded.status == EventStatus.FAILED.value
        assert "Max retries exceeded" in (reloaded.error_detail or "")
