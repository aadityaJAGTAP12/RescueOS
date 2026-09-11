"""
Phase 7B: Tests for Shared Operational Objects

Tests for Organization, Need, ResourceOffer, Operation, ActivityEvent, Notification
using the InMemoryRepository (no external dependencies).

Uses RELIEFOS_MEMORY=1 to ensure InMemoryRepository is used.
"""

# Repository selection: fresh_repo below explicitly sets an
# InMemoryRepository per test. No RELIEFOS_MEMORY env forcing — the
# import-time override poisoned the whole pytest process and silently
# downgraded DATABASE_URL runs to memory mode (Item 5B finding).

import pytest
from datetime import datetime, timezone, timedelta

from agent.data.models import (
    Organization, Need, ResourceOffer, Operation, ActivityEvent, Notification,
)
from agent.data.repository import get_repository, reset_repository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_repo():
    """Provide a fresh InMemoryRepository for each test.

    Explicitly selected (not env-forced) so the repository identity is
    provable regardless of the ambient DATABASE_URL (Item 5B).
    """
    reset_repository()
    from agent.data.repository import InMemoryRepository, set_repository
    repo = InMemoryRepository()
    set_repository(repo)
    yield repo
    reset_repository()


@pytest.fixture
def sample_org():
    return Organization(
        id="org_relief_india",
        name="Relief Services India",
        organization_type="ngo",
        description="Disaster relief organization",
        published_capabilities=["medical", "transport", "shelter"],
    )


@pytest.fixture
def sample_need():
    return Need(
        id="need_jorhat_food_20260729",
        need_type="food",
        title="Food shortage in Jorhat",
        description="2,000 people need food rations",
        district_id="jorhat",
        lat=26.74,
        lon=94.21,
        location_name="Jorhat",
        urgency="critical",
        status="OPEN",
        requested_resources=[{"type": "food", "quantity": 2000, "unit": "people"}],
        reporter_id="coordinator_1",
        reporter_type="coordinator",
        confidence=0.8,
    )


@pytest.fixture
def sample_offer(sample_org):
    return ResourceOffer(
        id="offer_org_b_boats",
        organization_id=sample_org.id,
        resource_type="boat",
        quantity=2,
        unit="units",
        lat=26.74,
        lon=94.21,
        location_name="Jorhat",
        district_id="jorhat",
        status="OFFERED",
        notes="2 rescue boats available immediately",
    )


@pytest.fixture
def sample_operation(sample_org, sample_need):
    return Operation(
        id="op_jorhat_rescue_1",
        name="Jorhat Rescue Operation",
        operation_type="rescue",
        description="Rescue operation in Jorhat flood zone",
        need_id=sample_need.id,
        lead_organization_id=sample_org.id,
        district_id="jorhat",
        lat=26.74,
        lon=94.21,
        location_name="Jorhat",
        status="PLANNING",
    )


# ---------------------------------------------------------------------------
# 1. Organization creation
# ---------------------------------------------------------------------------

class TestOrganization:
    def test_create_organization(self, fresh_repo, sample_org):
        result = fresh_repo.create_organization(sample_org)
        assert result.id == "org_relief_india"
        assert result.name == "Relief Services India"

    def test_get_organization(self, fresh_repo, sample_org):
        fresh_repo.create_organization(sample_org)
        fetched = fresh_repo.get_organization("org_relief_india")
        assert fetched is not None
        assert fetched.name == "Relief Services India"
        assert fetched.organization_type == "ngo"
        assert "medical" in fetched.published_capabilities

    def test_list_organizations_active_only(self, fresh_repo):
        org1 = Organization(id="org1", name="Org 1", active=True)
        org2 = Organization(id="org2", name="Org 2", active=False)
        fresh_repo.create_organization(org1)
        fresh_repo.create_organization(org2)
        
        active = fresh_repo.list_organizations(active_only=True)
        assert len(active) == 1
        assert active[0].id == "org1"
        
        all_orgs = fresh_repo.list_organizations(active_only=False)
        assert len(all_orgs) == 2

    def test_update_organization(self, fresh_repo, sample_org):
        fresh_repo.create_organization(sample_org)
        sample_org.name = "Updated Name"
        fresh_repo.update_organization(sample_org)
        fetched = fresh_repo.get_organization("org_relief_india")
        assert fetched.name == "Updated Name"

    def test_organization_to_dict(self, sample_org):
        d = sample_org.to_dict()
        assert d["id"] == "org_relief_india"
        assert d["name"] == "Relief Services India"
        assert d["organization_type"] == "ngo"
        assert "medical" in d["published_capabilities"]
        assert d["active"] is True


# ---------------------------------------------------------------------------
# 2. Need creation
# ---------------------------------------------------------------------------

class TestNeed:
    def test_create_need(self, fresh_repo, sample_need):
        result = fresh_repo.create_need(sample_need)
        assert result.id == "need_jorhat_food_20260729"
        assert result.need_type == "food"
        assert result.status == "OPEN"

    def test_get_need(self, fresh_repo, sample_need):
        fresh_repo.create_need(sample_need)
        fetched = fresh_repo.get_need("need_jorhat_food_20260729")
        assert fetched is not None
        assert fetched.title == "Food shortage in Jorhat"
        assert fetched.urgency == "critical"
        assert fetched.district_id == "jorhat"

    def test_list_needs_by_district(self, fresh_repo):
        need1 = Need(id="n1", need_type="food", title="Need 1", district_id="jorhat")
        need2 = Need(id="n2", need_type="water", title="Need 2", district_id="golaghat")
        fresh_repo.create_need(need1)
        fresh_repo.create_need(need2)
        
        jorhat_needs = fresh_repo.list_needs(district_id="jorhat")
        assert len(jorhat_needs) == 1
        assert jorhat_needs[0].district_id == "jorhat"

    def test_list_needs_by_status(self, fresh_repo):
        need1 = Need(id="n1", need_type="food", title="Need 1", status="OPEN")
        need2 = Need(id="n2", need_type="water", title="Need 2", status="RESOLVED")
        fresh_repo.create_need(need1)
        fresh_repo.create_need(need2)
        
        open_needs = fresh_repo.list_needs(status="OPEN")
        assert len(open_needs) == 1
        assert open_needs[0].status == "OPEN"

    def test_list_needs_by_urgency(self, fresh_repo):
        need1 = Need(id="n1", need_type="food", title="Need 1", urgency="critical")
        need2 = Need(id="n2", need_type="water", title="Need 2", urgency="low")
        fresh_repo.create_need(need1)
        fresh_repo.create_need(need2)
        
        critical_needs = fresh_repo.list_needs(urgency="critical")
        assert len(critical_needs) == 1
        assert critical_needs[0].urgency == "critical"

    def test_update_need(self, fresh_repo, sample_need):
        fresh_repo.create_need(sample_need)
        sample_need.title = "Updated food shortage"
        fresh_repo.update_need(sample_need)
        fetched = fresh_repo.get_need("need_jorhat_food_20260729")
        assert fetched.title == "Updated food shortage"

    def test_update_need_status(self, fresh_repo, sample_need):
        fresh_repo.create_need(sample_need)
        updated = fresh_repo.update_need_status("need_jorhat_food_20260729", "RESPONDING")
        assert updated is not None
        assert updated.status == "RESPONDING"
        assert updated.updated_at >= sample_need.created_at

    def test_update_need_status_nonexistent(self, fresh_repo):
        result = fresh_repo.update_need_status("nonexistent", "CLOSED")
        assert result is None

    def test_need_to_dict(self, sample_need):
        d = sample_need.to_dict()
        assert d["id"] == "need_jorhat_food_20260729"
        assert d["need_type"] == "food"
        assert d["urgency"] == "critical"
        assert d["status"] == "OPEN"
        assert len(d["requested_resources"]) == 1


# ---------------------------------------------------------------------------
# 3. Resource offer creation
# ---------------------------------------------------------------------------

class TestResourceOffer:
    def test_create_offer(self, fresh_repo, sample_offer):
        result = fresh_repo.create_resource_offer(sample_offer)
        assert result.id == "offer_org_b_boats"
        assert result.resource_type == "boat"
        assert result.quantity == 2

    def test_get_offer(self, fresh_repo, sample_offer):
        fresh_repo.create_resource_offer(sample_offer)
        fetched = fresh_repo.get_resource_offer("offer_org_b_boats")
        assert fetched is not None
        assert fetched.organization_id == "org_relief_india"
        assert fetched.status == "OFFERED"

    def test_list_offers_by_organization(self, fresh_repo, sample_offer):
        offer2 = ResourceOffer(
            id="offer2", organization_id="org_relief_india",
            resource_type="food", quantity=500, unit="kg",
        )
        fresh_repo.create_resource_offer(sample_offer)
        fresh_repo.create_resource_offer(offer2)
        
        org_offers = fresh_repo.list_resource_offers(organization_id="org_relief_india")
        assert len(org_offers) == 2

    def test_list_offers_by_district(self, fresh_repo, sample_offer):
        fresh_repo.create_resource_offer(sample_offer)
        jorhat_offers = fresh_repo.list_resource_offers(district_id="jorhat")
        assert len(jorhat_offers) == 1

    def test_list_offers_by_status(self, fresh_repo, sample_offer):
        fresh_repo.create_resource_offer(sample_offer)
        offered = fresh_repo.list_resource_offers(status="OFFERED")
        assert len(offered) == 1
        deployed = fresh_repo.list_resource_offers(status="DEPLOYED")
        assert len(deployed) == 0

    def test_list_offers_by_resource_type(self, fresh_repo, sample_offer):
        fresh_repo.create_resource_offer(sample_offer)
        boats = fresh_repo.list_resource_offers(resource_type="boat")
        assert len(boats) == 1
        food = fresh_repo.list_resource_offers(resource_type="food")
        assert len(food) == 0

    def test_update_offer(self, fresh_repo, sample_offer):
        fresh_repo.create_resource_offer(sample_offer)
        sample_offer.status = "ACCEPTED"
        fresh_repo.update_resource_offer(sample_offer)
        fetched = fresh_repo.get_resource_offer("offer_org_b_boats")
        assert fetched.status == "ACCEPTED"

    def test_offer_to_dict(self, sample_offer):
        d = sample_offer.to_dict()
        assert d["id"] == "offer_org_b_boats"
        assert d["resource_type"] == "boat"
        assert d["quantity"] == 2
        assert d["status"] == "OFFERED"

    def test_shared_objects_no_private_inventory(self, fresh_repo, sample_org, sample_offer):
        """Verify that published offers don't expose private inventory."""
        fresh_repo.create_organization(sample_org)
        fresh_repo.create_resource_offer(sample_offer)
        
        # Organization's published_capabilities are shared
        org = fresh_repo.get_organization(sample_org.id)
        assert "medical" in org.published_capabilities
        
        # But the org's full inventory is NOT stored
        # (there's no inventory field on Organization)
        assert not hasattr(org, 'full_inventory')
        assert not hasattr(org, 'staff_roster')


# ---------------------------------------------------------------------------
# 4. Operation creation
# ---------------------------------------------------------------------------

class TestOperation:
    def test_create_operation(self, fresh_repo, sample_operation):
        result = fresh_repo.create_operation(sample_operation)
        assert result.id == "op_jorhat_rescue_1"
        assert result.name == "Jorhat Rescue Operation"
        assert result.status == "PLANNING"

    def test_get_operation(self, fresh_repo, sample_operation):
        fresh_repo.create_operation(sample_operation)
        fetched = fresh_repo.get_operation("op_jorhat_rescue_1")
        assert fetched is not None
        assert fetched.operation_type == "rescue"
        assert fetched.lead_organization_id == "org_relief_india"

    def test_list_operations_by_district(self, fresh_repo):
        op1 = Operation(id="op1", name="Op 1", district_id="jorhat")
        op2 = Operation(id="op2", name="Op 2", district_id="golaghat")
        fresh_repo.create_operation(op1)
        fresh_repo.create_operation(op2)
        
        jorhat_ops = fresh_repo.list_operations(district_id="jorhat")
        assert len(jorhat_ops) == 1

    def test_list_operations_by_status(self, fresh_repo):
        op1 = Operation(id="op1", name="Op 1", status="ACTIVE")
        op2 = Operation(id="op2", name="Op 2", status="PLANNING")
        fresh_repo.create_operation(op1)
        fresh_repo.create_operation(op2)
        
        active_ops = fresh_repo.list_operations(status="ACTIVE")
        assert len(active_ops) == 1

    def test_list_operations_by_lead_org(self, fresh_repo, sample_operation):
        fresh_repo.create_operation(sample_operation)
        ops = fresh_repo.list_operations(lead_organization_id="org_relief_india")
        assert len(ops) == 1

    def test_update_operation(self, fresh_repo, sample_operation):
        fresh_repo.create_operation(sample_operation)
        sample_operation.status = "ACTIVE"
        fresh_repo.update_operation(sample_operation)
        fetched = fresh_repo.get_operation("op_jorhat_rescue_1")
        assert fetched.status == "ACTIVE"

    def test_add_operation_participant(self, fresh_repo, sample_operation):
        fresh_repo.create_operation(sample_operation)
        fresh_repo.add_operation_participant("op_jorhat_rescue_1", "org_relief_india", "lead")
        fresh_repo.add_operation_participant("op_jorhat_rescue_1", "org_medical_team", "support")
        
        participants = fresh_repo.list_operation_participants("op_jorhat_rescue_1")
        assert len(participants) == 2
        roles = [p["role"] for p in participants]
        assert "lead" in roles
        assert "support" in roles

    def test_operation_to_dict(self, sample_operation):
        d = sample_operation.to_dict()
        assert d["id"] == "op_jorhat_rescue_1"
        assert d["operation_type"] == "rescue"
        assert d["status"] == "PLANNING"
        assert d["lead_organization_id"] == "org_relief_india"


# ---------------------------------------------------------------------------
# 5. Activity event persistence
# ---------------------------------------------------------------------------

class TestActivityEvent:
    def test_append_activity_event(self, fresh_repo):
        event = ActivityEvent(
            id="evt_001",
            entity_type="need",
            entity_id="need_jorhat_food_20260729",
            event_type="need_created",
            actor="coordinator_1",
            detail="Need created for food shortage in Jorhat",
        )
        fresh_repo.append_activity_event(event)
        
        events = fresh_repo.list_activity_events(entity_type="need")
        assert len(events) == 1
        assert events[0].event_type == "need_created"

    def test_list_activity_events_by_entity(self, fresh_repo):
        event1 = ActivityEvent(
            id="evt_001", entity_type="need", entity_id="need_1",
            event_type="need_created", actor="user1",
        )
        event2 = ActivityEvent(
            id="evt_002", entity_type="need", entity_id="need_2",
            event_type="need_created", actor="user2",
        )
        event3 = ActivityEvent(
            id="evt_003", entity_type="operation", entity_id="op_1",
            event_type="operation_created", actor="user1",
        )
        fresh_repo.append_activity_event(event1)
        fresh_repo.append_activity_event(event2)
        fresh_repo.append_activity_event(event3)
        
        need_events = fresh_repo.list_activity_events(entity_type="need")
        assert len(need_events) == 2
        
        specific_need = fresh_repo.list_activity_events(entity_type="need", entity_id="need_1")
        assert len(specific_need) == 1

    def test_list_activity_events_limit(self, fresh_repo):
        for i in range(10):
            fresh_repo.append_activity_event(ActivityEvent(
                id=f"evt_{i:03d}", entity_type="need", entity_id="need_1",
                event_type="status_changed", actor="user1",
            ))
        
        events = fresh_repo.list_activity_events(limit=5)
        assert len(events) == 5

    def test_activity_events_sorted_by_created_at(self, fresh_repo):
        now = datetime.now(timezone.utc)
        event1 = ActivityEvent(
            id="evt_001", entity_type="need", entity_id="need_1",
            event_type="need_created", actor="user1",
            created_at=now,
        )
        event2 = ActivityEvent(
            id="evt_002", entity_type="need", entity_id="need_1",
            event_type="status_changed", actor="user1",
            created_at=now + timedelta(minutes=1),
        )
        fresh_repo.append_activity_event(event1)
        fresh_repo.append_activity_event(event2)
        
        events = fresh_repo.list_activity_events()
        assert events[0].id == "evt_002"  # Most recent first

    def test_activity_event_to_dict(self):
        event = ActivityEvent(
            id="evt_001", entity_type="need", entity_id="need_1",
            event_type="need_created", actor="user1", detail="Created a need",
        )
        d = event.to_dict()
        assert d["id"] == "evt_001"
        assert d["entity_type"] == "need"
        assert d["event_type"] == "need_created"


# ---------------------------------------------------------------------------
# 6. Notification persistence
# ---------------------------------------------------------------------------

class TestNotification:
    def test_create_notification(self, fresh_repo):
        notif = Notification(
            id="notif_001",
            recipient_id="coordinator_1",
            notification_type="urgent_need",
            title="New critical need in Jorhat",
            message="Food shortage for 2,000 people",
            entity_type="need",
            entity_id="need_jorhat_food_20260729",
        )
        result = fresh_repo.create_notification(notif)
        assert result.id == "notif_001"

    def test_list_notifications(self, fresh_repo):
        notif1 = Notification(
            id="notif_001", recipient_id="user1",
            notification_type="urgent_need", title="Need 1",
        )
        notif2 = Notification(
            id="notif_002", recipient_id="user1",
            notification_type="resource_offer", title="Offer 1",
        )
        notif3 = Notification(
            id="notif_003", recipient_id="user2",
            notification_type="urgent_need", title="Need 2",
        )
        fresh_repo.create_notification(notif1)
        fresh_repo.create_notification(notif2)
        fresh_repo.create_notification(notif3)
        
        user1_notifs = fresh_repo.list_notifications("user1")
        assert len(user1_notifs) == 2
        
        user2_notifs = fresh_repo.list_notifications("user2")
        assert len(user2_notifs) == 1

    def test_list_notifications_unread_only(self, fresh_repo):
        notif1 = Notification(
            id="notif_001", recipient_id="user1",
            notification_type="urgent_need", title="Need 1", read=False,
        )
        notif2 = Notification(
            id="notif_002", recipient_id="user1",
            notification_type="resource_offer", title="Offer 1", read=True,
        )
        fresh_repo.create_notification(notif1)
        fresh_repo.create_notification(notif2)
        
        unread = fresh_repo.list_notifications("user1", unread_only=True)
        assert len(unread) == 1
        assert unread[0].id == "notif_001"

    def test_mark_notification_read(self, fresh_repo):
        notif = Notification(
            id="notif_001", recipient_id="user1",
            notification_type="urgent_need", title="Need 1", read=False,
        )
        fresh_repo.create_notification(notif)
        
        fresh_repo.mark_notification_read("notif_001")
        
        unread = fresh_repo.list_notifications("user1", unread_only=True)
        assert len(unread) == 0
        
        all_notifs = fresh_repo.list_notifications("user1")
        assert len(all_notifs) == 1
        assert all_notifs[0].read is True

    def test_notification_to_dict(self):
        notif = Notification(
            id="notif_001", recipient_id="user1",
            notification_type="urgent_need", title="Need 1",
            message="Critical need", entity_type="need", entity_id="need_1",
        )
        d = notif.to_dict()
        assert d["id"] == "notif_001"
        assert d["notification_type"] == "urgent_need"
        assert d["read"] is False


# ---------------------------------------------------------------------------
# 7. Need status lifecycle
# ---------------------------------------------------------------------------

class TestNeedStatusLifecycle:
    def test_full_lifecycle(self, fresh_repo, sample_need):
        fresh_repo.create_need(sample_need)
        
        # OPEN → UNDER_REVIEW
        fresh_repo.update_need_status("need_jorhat_food_20260729", "UNDER_REVIEW")
        need = fresh_repo.get_need("need_jorhat_food_20260729")
        assert need.status == "UNDER_REVIEW"
        
        # UNDER_REVIEW → RESPONDING
        fresh_repo.update_need_status("need_jorhat_food_20260729", "RESPONDING")
        need = fresh_repo.get_need("need_jorhat_food_20260729")
        assert need.status == "RESPONDING"
        
        # RESPONDING → PARTIALLY_RESOLVED
        fresh_repo.update_need_status("need_jorhat_food_20260729", "PARTIALLY_RESOLVED")
        need = fresh_repo.get_need("need_jorhat_food_20260729")
        assert need.status == "PARTIALLY_RESOLVED"
        
        # PARTIALLY_RESOLVED → RESOLVED
        fresh_repo.update_need_status("need_jorhat_food_20260729", "RESOLVED")
        need = fresh_repo.get_need("need_jorhat_food_20260729")
        assert need.status == "RESOLVED"
        
        # RESOLVED → CLOSED
        fresh_repo.update_need_status("need_jorhat_food_20260729", "CLOSED")
        need = fresh_repo.get_need("need_jorhat_food_20260729")
        assert need.status == "CLOSED"


# ---------------------------------------------------------------------------
# 8. Cross-object integration
# ---------------------------------------------------------------------------

class TestCrossObjectIntegration:
    def test_organization_owning_resource_offer(self, fresh_repo, sample_org, sample_offer):
        fresh_repo.create_organization(sample_org)
        fresh_repo.create_resource_offer(sample_offer)
        
        # Verify the offer is linked to the organization
        offers = fresh_repo.list_resource_offers(organization_id=sample_org.id)
        assert len(offers) == 1
        assert offers[0].organization_id == sample_org.id

    def test_operation_linking_need_and_organization(self, fresh_repo, sample_org, sample_need, sample_operation):
        fresh_repo.create_organization(sample_org)
        fresh_repo.create_need(sample_need)
        fresh_repo.create_operation(sample_operation)
        
        # Verify the operation links to both
        op = fresh_repo.get_operation(sample_operation.id)
        assert op.need_id == sample_need.id
        assert op.lead_organization_id == sample_org.id

    def test_activity_events_for_cross_object_operations(self, fresh_repo, sample_org, sample_need, sample_operation):
        fresh_repo.create_organization(sample_org)
        fresh_repo.create_need(sample_need)
        
        # Record activity events
        fresh_repo.append_activity_event(ActivityEvent(
            id="evt_001", entity_type="need", entity_id=sample_need.id,
            event_type="need_created", actor="coordinator",
        ))
        fresh_repo.create_operation(sample_operation)
        fresh_repo.append_activity_event(ActivityEvent(
            id="evt_002", entity_type="operation", entity_id=sample_operation.id,
            event_type="operation_created", actor=sample_org.id,
        ))
        
        need_events = fresh_repo.list_activity_events(entity_type="need")
        assert len(need_events) == 1
        
        op_events = fresh_repo.list_activity_events(entity_type="operation")
        assert len(op_events) == 1


# ---------------------------------------------------------------------------
# 9. No district-specific logic
# ---------------------------------------------------------------------------

class TestDistrictAgnostic:
    def test_needs_work_across_districts(self, fresh_repo):
        districts = ["sivasagar", "jorhat", "charaideo", "golaghat"]
        for i, d in enumerate(districts):
            fresh_repo.create_need(Need(
                id=f"need_{d}", need_type="food", title=f"Need in {d}",
                district_id=d,
            ))
        
        for d in districts:
            needs = fresh_repo.list_needs(district_id=d)
            assert len(needs) == 1
            assert needs[0].district_id == d

    def test_operations_work_across_districts(self, fresh_repo):
        districts = ["sivasagar", "jorhat", "charaideo", "golaghat"]
        for i, d in enumerate(districts):
            fresh_repo.create_operation(Operation(
                id=f"op_{d}", name=f"Operation in {d}", district_id=d,
            ))
        
        for d in districts:
            ops = fresh_repo.list_operations(district_id=d)
            assert len(ops) == 1
            assert ops[0].district_id == d

    def test_resource_offers_work_across_districts(self, fresh_repo, sample_org):
        fresh_repo.create_organization(sample_org)
        districts = ["sivasagar", "jorhat", "charaideo", "golaghat"]
        for i, d in enumerate(districts):
            fresh_repo.create_resource_offer(ResourceOffer(
                id=f"offer_{d}", organization_id=sample_org.id,
                resource_type="boat", quantity=1, district_id=d,
            ))
        
        for d in districts:
            offers = fresh_repo.list_resource_offers(district_id=d)
            assert len(offers) == 1
            assert offers[0].district_id == d
