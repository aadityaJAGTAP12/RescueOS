"""
Tests for Notification Event Generation (Item #6)

Verifies:
1. Notification CRUD & Repository: creation, recipient filtering, unread filter, mark as read.
2. Proposal Lifecycle Event Generation: notifications and activity events emitted across
   propose, send-to-org, evaluate, approve-publication, and decline.
3. Privacy Boundary: notifications never contain private_factors or private NGO data.
4. Multi-Org Isolation: org_beta cannot see notifications addressed to org_alpha.
5. Session Seam Integration: GET /api/notifications resolves session org when recipient_id is omitted.
"""

import uuid
import pytest
from datetime import datetime, timezone

from agent.data.models import Notification, Need, Organization
from agent.data.repository import get_repository, reset_repository


@pytest.fixture
def client():
    from agent.api import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def test_org_a(client):
    repo = get_repository()
    org_id = "org_notif_a"
    existing = repo.get_organization(org_id)
    if existing:
        return existing
    org = Organization(
        id=org_id,
        name="Notification Org Alpha",
        organization_type="ngo",
        active=True,
    )
    return repo.create_organization(org)


@pytest.fixture
def test_org_b(client):
    repo = get_repository()
    org_id = "org_notif_b"
    existing = repo.get_organization(org_id)
    if existing:
        return existing
    org = Organization(
        id=org_id,
        name="Notification Org Beta",
        organization_type="ngo",
        active=True,
    )
    return repo.create_organization(org)


@pytest.fixture
def test_need(client):
    repo = get_repository()
    need_id = f"need_notif_{uuid.uuid4().hex[:6]}"
    need = Need(
        id=need_id,
        need_type="water",
        title="Urgent Water Shortage",
        district_id="jorhat",
        urgency="critical",
        status="OPEN",
        requested_resources=[{"type": "water", "quantity": 100, "unit": "kits"}],
    )
    return repo.create_need(need)


class TestNotificationRepository:
    def test_create_and_retrieve_notification(self, test_org_a):
        repo = get_repository()
        notif_id = f"notif_{uuid.uuid4().hex[:8]}"
        notif = Notification(
            id=notif_id,
            recipient_id=test_org_a.id,
            notification_type="test_notification",
            title="Test Title",
            message="Test notification message",
            entity_type="coordination",
            entity_id="prop_test",
            read=False,
            metadata={"source": "test"},
        )
        created = repo.create_notification(notif)
        assert created.id == notif_id

        notifs = repo.list_notifications(recipient_id=test_org_a.id)
        matching = [n for n in notifs if n.id == notif_id]
        assert len(matching) == 1
        assert matching[0].title == "Test Title"
        assert matching[0].read is False

    def test_unread_only_filtering_and_mark_read(self, test_org_b):
        repo = get_repository()
        n1 = Notification(
            id=f"notif_{uuid.uuid4().hex[:8]}",
            recipient_id=test_org_b.id,
            notification_type="test",
            title="Unread 1",
            read=False,
        )
        n2 = Notification(
            id=f"notif_{uuid.uuid4().hex[:8]}",
            recipient_id=test_org_b.id,
            notification_type="test",
            title="Unread 2",
            read=False,
        )
        repo.create_notification(n1)
        repo.create_notification(n2)

        # Mark n1 as read
        repo.mark_notification_read(n1.id)

        all_notifs = repo.list_notifications(recipient_id=test_org_b.id, unread_only=False)
        unread_notifs = repo.list_notifications(recipient_id=test_org_b.id, unread_only=True)

        assert any(n.id == n1.id for n in all_notifs)
        assert any(n.id == n2.id for n in all_notifs)
        assert not any(n.id == n1.id for n in unread_notifs)
        assert any(n.id == n2.id for n in unread_notifs)


class TestProposalLifecycleNotificationEmission:
    def test_coordination_propose_creates_notification_and_activity(self, client, test_org_a, test_need):
        resp = client.post(
            "/api/network/coordination/propose",
            json={
                "need": test_need.to_dict(),
                "organization_id": test_org_a.id,
                "organization_name": test_org_a.name,
            },
        )
        assert resp.status_code == 201, resp.get_json()
        proposal_id = resp.get_json()["proposal"]["id"]

        repo = get_repository()
        # Verify notification created for target org
        notifs = repo.list_notifications(recipient_id=test_org_a.id)
        matching = [n for n in notifs if n.entity_id == proposal_id]
        assert len(matching) >= 1
        assert matching[0].notification_type == "coordination_proposed"
        assert matching[0].read is False

        # Verify activity event
        events = repo.list_activity_events(entity_type="coordination", entity_id=proposal_id)
        assert any(e.event_type == "coordination_proposed" for e in events)

    def test_send_to_org_creates_targeted_notification_and_activity(self, client, test_org_a, test_need):
        # Create proposal first
        resp = client.post(
            "/api/network/coordination/propose",
            json={
                "need": test_need.to_dict(),
                "organization_id": test_org_a.id,
                "organization_name": test_org_a.name,
            },
        )
        proposal_id = resp.get_json()["proposal"]["id"]

        # Send to org
        resp = client.post(f"/api/network/coordination/proposals/{proposal_id}/send-to-org")
        assert resp.status_code == 200, resp.get_json()

        repo = get_repository()
        # Check notification for target org
        notifs = repo.list_notifications(recipient_id=test_org_a.id)
        received_notifs = [n for n in notifs if n.entity_id == proposal_id and n.notification_type == "coordination_proposal_received"]
        assert len(received_notifs) == 1
        assert "requires evaluation" in received_notifs[0].message

        # Check activity event
        events = repo.list_activity_events(entity_type="coordination", entity_id=proposal_id)
        assert any(e.event_type == "proposal_sent_to_org" for e in events)

    def test_evaluate_creates_recommendation_notification(self, client, test_org_a, test_need):
        # Propose and send
        resp = client.post(
            "/api/network/coordination/propose",
            json={
                "need": test_need.to_dict(),
                "organization_id": test_org_a.id,
                "organization_name": test_org_a.name,
            },
        )
        proposal_id = resp.get_json()["proposal"]["id"]
        client.post(f"/api/network/coordination/proposals/{proposal_id}/send-to-org")

        # Evaluate with session org cookie
        client.set_cookie("reliefos_org_id", test_org_a.id)
        resp = client.post(
            "/api/my-org/agent/evaluate-coordination",
            json={"proposal_id": proposal_id},
        )
        assert resp.status_code == 200, resp.get_json()

        repo = get_repository()
        notifs = repo.list_notifications(recipient_id=test_org_a.id)
        eval_notifs = [n for n in notifs if n.entity_id == proposal_id and n.notification_type == "coordination_recommendation_ready"]
        assert len(eval_notifs) == 1
        assert "Awaiting human approval" in eval_notifs[0].message

        events = repo.list_activity_events(entity_type="coordination", entity_id=proposal_id)
        assert any(e.event_type == "organization_evaluation_completed" for e in events)

    def test_approve_publication_creates_network_broadcast_notification(self, client, test_org_a, test_need):
        # Propose, send, evaluate
        resp = client.post(
            "/api/network/coordination/propose",
            json={
                "need": test_need.to_dict(),
                "organization_id": test_org_a.id,
                "organization_name": test_org_a.name,
            },
        )
        proposal_id = resp.get_json()["proposal"]["id"]
        client.post(f"/api/network/coordination/proposals/{proposal_id}/send-to-org")
        client.set_cookie("reliefos_org_id", test_org_a.id)
        client.post(
            "/api/my-org/resources",
            json={"resource_type": "water", "quantity": 10, "unit": "liters"},
        )
        client.post("/api/my-org/agent/evaluate-coordination", json={"proposal_id": proposal_id})

        # Human approve
        resp = client.post("/api/my-org/agent/approve-publication", json={"proposal_id": proposal_id})
        assert resp.status_code == 200, resp.get_json()

        repo = get_repository()
        # Network broadcast notification
        notifs = repo.list_notifications(recipient_id="network")
        pub_notifs = [n for n in notifs if n.entity_id == proposal_id and n.notification_type == "coordination_offer_published"]
        assert len(pub_notifs) == 1
        assert "approved and published offer" in pub_notifs[0].message

        # Activity events include proposal_confirmed
        events = repo.list_activity_events(entity_type="coordination", entity_id=proposal_id)
        assert any(e.event_type == "proposal_confirmed" for e in events)

    def test_decline_creates_network_notification_and_activity(self, client, test_org_a, test_need):
        resp = client.post(
            "/api/network/coordination/propose",
            json={
                "need": test_need.to_dict(),
                "organization_id": test_org_a.id,
                "organization_name": test_org_a.name,
            },
        )
        proposal_id = resp.get_json()["proposal"]["id"]

        resp = client.post(f"/api/network/coordination/proposals/{proposal_id}/decline")
        assert resp.status_code == 200, resp.get_json()

        repo = get_repository()
        notifs = repo.list_notifications(recipient_id="network")
        dec_notifs = [n for n in notifs if n.entity_id == proposal_id and n.notification_type == "coordination_proposal_declined"]
        assert len(dec_notifs) == 1

        events = repo.list_activity_events(entity_type="coordination", entity_id=proposal_id)
        assert any(e.event_type == "proposal_declined" for e in events)


class TestNotificationPrivacyAndIsolation:
    def test_notification_payload_never_leaks_private_factors(self, client, test_org_a, test_need):
        resp = client.post(
            "/api/network/coordination/propose",
            json={
                "need": test_need.to_dict(),
                "organization_id": test_org_a.id,
                "organization_name": test_org_a.name,
            },
        )
        proposal_id = resp.get_json()["proposal"]["id"]
        client.post(f"/api/network/coordination/proposals/{proposal_id}/send-to-org")
        client.set_cookie("reliefos_org_id", test_org_a.id)
        client.post("/api/my-org/agent/evaluate-coordination", json={"proposal_id": proposal_id})

        repo = get_repository()
        all_notifs = repo.list_notifications(recipient_id=test_org_a.id)
        for n in all_notifs:
            text = f"{n.title} {n.message} {str(n.metadata)}"
            assert "private_factors" not in text
            assert "private_reasoning" not in text
            assert "secret" not in text.lower()

    def test_multi_org_notification_isolation(self, client, test_org_a, test_org_b, test_need):
        # Create notification targeted at org A
        resp = client.post(
            "/api/network/coordination/propose",
            json={
                "need": test_need.to_dict(),
                "organization_id": test_org_a.id,
                "organization_name": test_org_a.name,
            },
        )
        proposal_id = resp.get_json()["proposal"]["id"]
        client.post(f"/api/network/coordination/proposals/{proposal_id}/send-to-org")

        # Query notifications for Org A
        resp_a = client.get(f"/api/notifications?recipient_id={test_org_a.id}")
        assert resp_a.status_code == 200
        notifs_a = resp_a.get_json()["notifications"]
        assert any(n["entity_id"] == proposal_id for n in notifs_a)

        # Query notifications for Org B — must NOT contain Org A's proposal notification
        resp_b = client.get(f"/api/notifications?recipient_id={test_org_b.id}")
        assert resp_b.status_code == 200
        notifs_b = resp_b.get_json()["notifications"]
        assert not any(n["entity_id"] == proposal_id for n in notifs_b)

    def test_get_notifications_with_session_cookie(self, client, test_org_a, test_need):
        resp = client.post(
            "/api/network/coordination/propose",
            json={
                "need": test_need.to_dict(),
                "organization_id": test_org_a.id,
                "organization_name": test_org_a.name,
            },
        )
        proposal_id = resp.get_json()["proposal"]["id"]

        # Without recipient_id param, use cookie
        client.set_cookie("reliefos_org_id", test_org_a.id)
        resp = client.get("/api/notifications")
        assert resp.status_code == 200
        notifs = resp.get_json()["notifications"]
        assert any(n["entity_id"] == proposal_id for n in notifs)

    def test_api_mark_notification_read(self, client, test_org_a):
        repo = get_repository()
        notif_id = f"notif_{uuid.uuid4().hex[:8]}"
        repo.create_notification(Notification(
            id=notif_id,
            recipient_id=test_org_a.id,
            notification_type="test",
            title="To Read",
            read=False,
        ))

        # Mark read via API
        resp = client.post(f"/api/notifications/{notif_id}/read")
        assert resp.status_code == 200, resp.get_json()

        # Check unread query
        resp_unread = client.get(f"/api/notifications?recipient_id={test_org_a.id}&unread_only=true")
        notifs = resp_unread.get_json()["notifications"]
        assert not any(n["id"] == notif_id for n in notifs)
