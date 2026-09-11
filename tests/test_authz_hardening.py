"""
ReliefOS Production Hardening — Adversarial Auth/AuthZ, Startup & Durability Tests

Covers the security model end to end:

  Authentication  : unauthenticated / invalid / expired sessions fail closed
                    when AUTH_ENFORCED=true; authenticated requests succeed.
  Authorization   : membership-scoped org context — user A (org A) can act on
                    org A only; forged org cookies, body org_id spoofing, and
                    cross-org offer/proposal/notification/agent-state access
                    all fail safely.
  Audit           : consequential actions record actor/org/entity/transitions.
  Security        : internal exception details are never returned to clients.
  Startup         : mandatory runtime component failures abort startup;
                    optional ones degrade loudly.
  Persistence     : restart durability, transaction rollback, event-claim
                    atomicity (backend-specific where meaningful).

Dev/test fallback semantics (unauthenticated access allowed when
AUTH_ENFORCED is not set) are intentionally preserved and covered by the
existing functional suites; every enforced-mode test here patches
AUTH_ENFORCED=true explicitly.
"""

import os
import time
import uuid
from datetime import datetime, timezone

import pytest
from unittest.mock import patch

from agent.api import app
from agent.auth.models import User, UserRole
from agent.auth.service import AuthService, create_session_token
from agent.data.repository import get_repository, reset_repository, InMemoryRepository
from agent.org_context import SESSION_COOKIE_NAME


TEST_SECRET = "test-secret-key-12345678901234567890"
RUN_TAG = uuid.uuid4().hex[:8]


@pytest.fixture
def client():
    app.config["TESTING"] = True
    # Bind ONE AuthService (same secret + same repository) to the app so
    # tokens minted via the service verify through the app's resolver.
    app.auth_service = AuthService(repository=get_repository(), secret_key=TEST_SECRET)
    with app.test_client() as c:
        yield c


def _auth_service():
    return app.auth_service


def _register_user(username_prefix: str, org_id: str, role: UserRole = UserRole.ORG_OPERATOR):
    """Create a user with a membership directly through the service layer."""
    svc = _auth_service()
    suffix = uuid.uuid4().hex[:8]
    user, _ = svc.register_user(
        username=f"{username_prefix}_{suffix}",
        email=f"{username_prefix}_{suffix}@example.test",
        password="Str0ngPassw0rd!",
        initial_org_id=org_id,
        initial_role=role,
    )
    return svc, user


def _ensure_org(org_id: str):
    from agent.data.models import Organization
    repo = get_repository()
    if not repo.get_organization(org_id):
        repo.create_organization(Organization(id=org_id, name=f"Org {org_id}", organization_type="ngo"))


def _org_a() -> str:
    return f"org_az_{RUN_TAG}"


def _org_b() -> str:
    return f"org_bz_{RUN_TAG}"


ENFORCED = {"AUTH_ENFORCED": "true"}


def _delete_agent_events(repo, event_ids) -> None:
    """Test cleanup that works against both repository backends."""
    if not event_ids:
        return
    if hasattr(repo, "_engine") and repo._engine is not None:
        from agent.data.schema import agent_events as ae_table
        from sqlalchemy import delete
        with repo._engine.begin() as conn:
            conn.execute(ae_table.delete().where(ae_table.c.id.in_(list(event_ids))))
    elif hasattr(repo, "_agent_events"):
        for eid in list(event_ids):
            repo._agent_events.pop(eid, None)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestAuthenticationBoundary:
    def test_unauthenticated_my_org_access_denied_when_enforced(self, client):
        with patch.dict(os.environ, ENFORCED):
            resp = client.get("/api/my-org/summary")
        assert resp.status_code == 401
        assert resp.get_json()["code"] == "UNAUTHORIZED"

    def test_unauthenticated_session_org_selection_denied_when_enforced(self, client):
        _ensure_org(_org_a())
        with patch.dict(os.environ, ENFORCED):
            resp = client.post("/api/session/org", json={"org_id": _org_a()})
        assert resp.status_code == 401

    def test_invalid_session_token_denied_when_enforced(self, client):
        with patch.dict(os.environ, ENFORCED):
            resp = client.get(
                "/api/my-org/summary",
                headers={"Authorization": "Bearer not-a-real-token"},
            )
        assert resp.status_code == 401

    def test_tampered_token_denied_when_enforced(self, client):
        svc, user = _register_user("tamper", _org_a())
        token = svc.create_token_for_user(user)
        tampered = token[:-6] + "aaaaaa"
        with patch.dict(os.environ, ENFORCED):
            resp = client.get("/api/my-org/summary", headers={"Authorization": f"Bearer {tampered}"})
        assert resp.status_code == 401

    def test_expired_session_denied_when_enforced(self, client):
        svc, user = _register_user("expired", _org_a())
        # Mint a token that expired 60s ago.
        token = create_session_token(
            user_id=user.id, username=user.username,
            secret_key=svc.secret_key, expires_in_seconds=-60,
        )
        with patch.dict(os.environ, ENFORCED):
            resp = client.get("/api/my-org/summary", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_authenticated_request_succeeds_when_enforced(self, client):
        org = _org_a()
        _ensure_org(org)
        svc, user = _register_user("valid", org)
        token = svc.create_token_for_user(user)
        with patch.dict(os.environ, ENFORCED):
            client.set_cookie(SESSION_COOKIE_NAME, org)
            resp = client.get("/api/my-org/summary", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["org_id"] == org

    def test_agent_state_requires_authentication_when_enforced(self, client):
        with patch.dict(os.environ, ENFORCED):
            for path in (
                "/api/agent/events",
                "/api/agent/proactive/scans",
                "/api/agent/proactive/findings",
                "/api/field-intelligence/history",
            ):
                resp = client.get(path)
                assert resp.status_code == 401, f"{path} -> {resp.status_code}"


# ---------------------------------------------------------------------------
# Authorization — membership-scoped org context
# ---------------------------------------------------------------------------

class TestOrganizationAuthorization:
    def test_user_a_can_select_own_org(self, client):
        org_a = _org_a()
        _ensure_org(org_a)
        svc, user = _register_user("ua", org_a)
        token = svc.create_token_for_user(user)
        with patch.dict(os.environ, ENFORCED):
            resp = client.post(
                "/api/session/org", json={"org_id": org_a},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.get_json()

    def test_user_a_cannot_select_org_b(self, client):
        org_a, org_b = _org_a(), _org_b()
        _ensure_org(org_a)
        _ensure_org(org_b)
        svc, user = _register_user("ua2", org_a)
        token = svc.create_token_for_user(user)
        with patch.dict(os.environ, ENFORCED):
            resp = client.post(
                "/api/session/org", json={"org_id": org_b},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403
        assert resp.get_json()["code"] == "FORBIDDEN"

    def test_forged_org_cookie_cannot_grant_org_b(self, client):
        """User A forges reliefos_org_id=orgB: the resolved org context must
        stay org A (membership wins over the cookie)."""
        org_a, org_b = _org_a(), _org_b()
        _ensure_org(org_a)
        _ensure_org(org_b)
        svc, user = _register_user("ua3", org_a)
        token = svc.create_token_for_user(user)
        with patch.dict(os.environ, ENFORCED):
            client.set_cookie(SESSION_COOKIE_NAME, org_b)  # forged
            resp = client.get("/api/my-org/summary", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.get_json()["org_id"] == org_a

    def test_body_org_id_spoofing_ignored_for_offers(self, client):
        org_a, org_b = _org_a(), _org_b()
        _ensure_org(org_a)
        _ensure_org(org_b)
        svc, user = _register_user("ua4", org_a)
        token = svc.create_token_for_user(user)
        with patch.dict(os.environ, ENFORCED):
            client.set_cookie(SESSION_COOKIE_NAME, org_a)
            resp = client.post(
                "/api/offers",
                json={"resource_type": "water", "quantity": 5, "unit": "liters",
                      "organization_id": org_b},  # spoofed
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 201, resp.get_json()
        assert resp.get_json()["offer"]["organization_id"] == org_a

    def test_cross_org_offer_patch_denied(self, client):
        org_a, org_b = _org_a(), _org_b()
        _ensure_org(org_a)
        _ensure_org(org_b)
        from agent.data.models import ResourceOffer
        repo = get_repository()
        now = datetime.now(timezone.utc)
        offer = repo.create_resource_offer(ResourceOffer(
            id=f"offer_xo_{RUN_TAG}", organization_id=org_b, resource_type="water",
            quantity=3, unit="liters", status="OFFERED", created_at=now, updated_at=now,
        ))
        svc, user = _register_user("ua5", org_a)
        token = svc.create_token_for_user(user)
        with patch.dict(os.environ, ENFORCED):
            client.set_cookie(SESSION_COOKIE_NAME, org_a)
            resp = client.patch(
                f"/api/offers/{offer.id}", json={"status": "ACCEPTED"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403
        # The offer must be untouched.
        assert repo.get_resource_offer(offer.id).status == "OFFERED"

    def test_cross_org_notification_list_denied(self, client):
        org_a, org_b = _org_a(), _org_b()
        _ensure_org(org_a)
        _ensure_org(org_b)
        svc, user = _register_user("ua6", org_a)
        token = svc.create_token_for_user(user)
        with patch.dict(os.environ, ENFORCED):
            client.set_cookie(SESSION_COOKIE_NAME, org_a)
            resp = client.get(
                f"/api/notifications?recipient_id={org_b}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403

    def test_cross_org_notification_mark_read_denied(self, client):
        org_a, org_b = _org_a(), _org_b()
        _ensure_org(org_a)
        _ensure_org(org_b)
        from agent.data.models import Notification
        repo = get_repository()
        notif = repo.create_notification(Notification(
            id=f"notif_xo_{RUN_TAG}", recipient_id=org_b, notification_type="test",
            title="T", message="m", entity_type="test", entity_id="e",
        ))
        svc, user = _register_user("ua7", org_a)
        token = svc.create_token_for_user(user)
        with patch.dict(os.environ, ENFORCED):
            client.set_cookie(SESSION_COOKIE_NAME, org_a)
            resp = client.post(
                f"/api/notifications/{notif.id}/read",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403
        assert repo.get_notification(notif.id).read is False

    def test_cross_org_proposal_evaluation_denied(self, client):
        """Org B cannot evaluate (or approve publication for) a proposal
        targeting org A — even with a valid authenticated session for B."""
        org_a, org_b = _org_a(), _org_b()
        _ensure_org(org_a)
        _ensure_org(org_b)
        from agent.coordination.proposal import create_proposal
        proposal = create_proposal(
            need_id=f"need_{RUN_TAG}", organization_id=org_a,
            organization_name="Org A", proposal_type="water",
            summary="s", public_evidence=[], network_findings=[],
        )
        svc, user = _register_user("ub1", org_b, role=UserRole.ORG_ADMIN)
        token = svc.create_token_for_user(user)
        with patch.dict(os.environ, ENFORCED):
            client.set_cookie(SESSION_COOKIE_NAME, org_b)
            for path, body in (
                ("/api/my-org/agent/evaluate-coordination", {"proposal_id": proposal["id"]}),
                ("/api/my-org/agent/approve-publication", {"proposal_id": proposal["id"]}),
            ):
                resp = client.post(path, json=body, headers={"Authorization": f"Bearer {token}"})
                assert resp.status_code == 404, f"{path} -> {resp.status_code}"

    def test_network_operator_endpoints_denied_for_org_users(self, client):
        org_a = _org_a()
        _ensure_org(org_a)
        svc, user = _register_user("ua8", org_a)
        token = svc.create_token_for_user(user)
        with patch.dict(os.environ, ENFORCED):
            client.set_cookie(SESSION_COOKIE_NAME, org_a)
            resp = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 403
            resp = client.post(
                "/api/network/coordination/propose",
                json={"need": {"id": "n1"}, "organization_id": org_a},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403

    def test_network_operator_can_access_audit(self, client):
        svc, user = _register_user("netop", _org_a(), role=UserRole.NETWORK_OPERATOR)
        token = svc.create_token_for_user(user)
        with patch.dict(os.environ, ENFORCED):
            resp = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Consequential-action audit records
# ---------------------------------------------------------------------------

class TestConsequentialActionAudit:
    def test_publish_offer_audit_record(self, client):
        org_a = _org_a()
        _ensure_org(org_a)
        svc, user = _register_user("audit1", org_a)
        token = svc.create_token_for_user(user)
        with patch.dict(os.environ, ENFORCED):
            client.set_cookie(SESSION_COOKIE_NAME, org_a)
            resp = client.post(
                "/api/offers",
                json={"resource_type": "water", "quantity": 2, "unit": "liters"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 201
        offer_id = resp.get_json()["offer"]["id"]

        logs = get_repository().list_audit_logs(action="publish_offer", limit=50)
        entry = next((l for l in logs if l.entity_id == offer_id), None)
        assert entry is not None, "publish_offer audit record missing"
        assert entry.entity_type == "offer"
        assert entry.organization_id == org_a
        assert entry.to_state == "OFFERED"
        assert entry.actor_id == user.id

    def test_notification_read_audit_record(self, client):
        org_a = _org_a()
        _ensure_org(org_a)
        from agent.data.models import Notification
        repo = get_repository()
        notif = repo.create_notification(Notification(
            id=f"notif_aud_{RUN_TAG}", recipient_id=org_a, notification_type="test",
            title="T", message="m", entity_type="test", entity_id="e",
        ))
        svc, user = _register_user("audit2", org_a)
        token = svc.create_token_for_user(user)
        with patch.dict(os.environ, ENFORCED):
            client.set_cookie(SESSION_COOKIE_NAME, org_a)
            resp = client.post(
                f"/api/notifications/{notif.id}/read",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        logs = repo.list_audit_logs(action="mark_notification_read", limit=50)
        entry = next((l for l in logs if l.entity_id == notif.id), None)
        assert entry is not None
        assert (entry.from_state, entry.to_state) == ("UNREAD", "READ")

    def test_confirm_match_audit_record(self, client):
        """Match confirmation is the critical human commitment — it must be
        audited with actor, org, entity and the need's state transition."""
        org_a = _org_a()
        _ensure_org(org_a)
        from agent.data.models import Need, ResourceOffer
        repo = get_repository()
        now = datetime.now(timezone.utc)
        need = repo.create_need(Need(
            id=f"need_am_{RUN_TAG}", need_type="water", title="audit match",
            district_id=None, lat=26.7, lon=94.2, urgency="high", status="OPEN",
            created_at=now, updated_at=now,
        ))
        offer = repo.create_resource_offer(ResourceOffer(
            id=f"offer_am_{RUN_TAG}", organization_id=org_a, resource_type="water",
            quantity=5, unit="liters", status="OFFERED", created_at=now, updated_at=now,
        ))
        svc, user = _register_user("audit3", org_a)
        token = svc.create_token_for_user(user)
        with patch.dict(os.environ, ENFORCED):
            resp = client.post(
                f"/api/matches/{need.id}/{offer.id}/confirm",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 201, resp.get_json()
        op_id = resp.get_json()["operation"]["id"]
        logs = repo.list_audit_logs(action="confirm_match", limit=50)
        entry = next((l for l in logs if l.entity_id == op_id), None)
        assert entry is not None
        assert entry.details.get("need_id") == need.id
        assert entry.details.get("offer_id") == offer.id


# ---------------------------------------------------------------------------
# Security — error sanitization
# ---------------------------------------------------------------------------

class TestErrorSanitization:
    def test_internal_exception_details_not_returned(self, client):
        """Even outside production mode, handler-level _api_error responses
        must not carry exception text."""
        from agent.api import app as flask_app

        def boom():
            raise RuntimeError("SECRET DB DSN postgresql://user:pass@host/db")

        original = flask_app.view_functions.get("api_list_activity")
        try:
            flask_app.view_functions["api_list_activity"] = boom
            resp = client.get("/api/activity")
            assert resp.status_code == 500
            body = str(resp.get_json())
            assert "SECRET DB DSN" not in body
            assert "postgresql://" not in body
        finally:
            if original:
                flask_app.view_functions["api_list_activity"] = original

    def test_production_500_body_is_generic(self, client):
        from agent.api import app as flask_app

        def boom():
            raise RuntimeError("stack trace detail with filesystem paths")

        original = flask_app.view_functions.get("api_list_activity")
        try:
            flask_app.view_functions["api_list_activity"] = boom
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                resp = client.get("/api/activity")
            assert resp.status_code == 500
            body = str(resp.get_json())
            assert "stack trace detail" not in body
            assert "RuntimeError" not in body
        finally:
            if original:
                flask_app.view_functions["api_list_activity"] = original


# ---------------------------------------------------------------------------
# Startup hardening
# ---------------------------------------------------------------------------

class TestStartupHardening:
    def _fresh_settings(self, monkeypatch):
        from agent.config import get_settings
        settings = get_settings()
        monkeypatch.setattr(settings, "event_worker_enabled", True, raising=False)
        monkeypatch.setattr(settings, "event_worker_required", True, raising=False)
        monkeypatch.setattr(settings, "proactive_scheduler_enabled", False, raising=False)
        return settings

    def test_event_worker_failure_is_fatal(self, monkeypatch):
        self._fresh_settings(monkeypatch)

        import agent.prod_startup as startup
        import agent.agents.event_router as event_router

        def _boom(**kwargs):
            raise RuntimeError("worker thread could not start")

        # Simulate a worker that starts but is instantly dead.
        class DeadThread:
            def is_alive(self):
                return False

        monkeypatch.setattr(event_router, "start_event_worker", lambda **kw: None)
        # And make the "started" detection see a dead/absent thread.
        called = {}
        real_init = startup.init_production_application

        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            with patch.object(startup, "start_event_worker_loop", side_effect=_boom):
                # init_production_application imports start_event_worker from
                # event_router directly — patch it there.
                monkeypatch.setattr(event_router, "start_event_worker",
                                    lambda **kw: (_ for _ in ()).throw(RuntimeError("no worker")))
                with pytest.raises(RuntimeError, match="Mandatory startup components failed"):
                    real_init()

    def test_proactive_scheduler_failure_degrades_by_default(self, monkeypatch):
        settings = self._fresh_settings(monkeypatch)
        monkeypatch.setattr(settings, "proactive_scheduler_enabled", True, raising=False)
        monkeypatch.setattr(settings, "proactive_scheduler_required", False, raising=False)
        # Keep the outbox worker out of these tests so it cannot compete for
        # pending events in the persistence suite.
        monkeypatch.setattr(settings, "event_worker_enabled", False, raising=False)

        import agent.prod_startup as startup
        import agent.proactive.scheduler as scheduler_mod

        def _boom(interval_seconds=None):
            raise RuntimeError("scheduler thread error")

        monkeypatch.setattr(scheduler_mod, "start_proactive_scheduler", _boom)
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            app = startup.init_production_application()
        assert app is not None  # degraded, not aborted

    def test_proactive_scheduler_failure_fatal_when_required(self, monkeypatch):
        settings = self._fresh_settings(monkeypatch)
        monkeypatch.setattr(settings, "proactive_scheduler_enabled", True, raising=False)
        monkeypatch.setattr(settings, "proactive_scheduler_required", True, raising=False)
        monkeypatch.setattr(settings, "event_worker_enabled", False, raising=False)

        import agent.prod_startup as startup
        import agent.proactive.scheduler as scheduler_mod

        def _boom(interval_seconds=None):
            raise RuntimeError("scheduler thread error")

        monkeypatch.setattr(scheduler_mod, "start_proactive_scheduler", _boom)
        with pytest.raises(RuntimeError, match="Mandatory startup components failed"):
            startup.init_production_application()

    def test_worker_starts_and_thread_is_alive(self, monkeypatch):
        self._fresh_settings(monkeypatch)
        import agent.prod_startup as startup
        import agent.agents.event_router as event_router

        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            startup.init_production_application()
        try:
            assert event_router._worker_thread is not None
            assert event_router._worker_thread.is_alive()
            assert event_router._recovery_thread is not None
        finally:
            event_router.stop_event_worker(timeout=5)
            event_router.stop_stale_recovery_loop(timeout=5)


# ---------------------------------------------------------------------------
# Persistence — durability, rollback, claim atomicity
# ---------------------------------------------------------------------------

class TestPersistence:
    def setup_method(self):
        """Ensure no background event worker from startup tests is competing
        for pending outbox events during claim-atomicity assertions."""
        from agent.agents import event_router
        event_router.stop_event_worker(timeout=5)
        event_router.stop_stale_recovery_loop(timeout=5)

    def test_event_claiming_excludes_claimed_events(self):
        """Sequential claims must never return the same event twice."""
        from agent.data.models import AgentEvent, AgentEventType, EventStatus
        repo = get_repository()
        now = datetime.now(timezone.utc)
        ids = set()
        for i in range(3):
            ev = AgentEvent(
                event_id=f"evt_claim_{RUN_TAG}_{i}", event_type=AgentEventType.NEED_CREATED,
                status=EventStatus.PENDING, created_at=now.isoformat(),
                metadata={}, organization_id=None,
            )
            repo.append_agent_event(ev)
            ids.add(ev.event_id)

        try:
            # Claim everything pending (the shared dev DB may hold a backlog;
            # FIFO ordering means our events may not be first).
            first = repo.claim_pending_agent_events(limit=10000)
            first_ids = {e.event_id for e in first if e.event_id in ids}
            second = repo.claim_pending_agent_events(limit=10000)
            second_ids = {e.event_id for e in second if e.event_id in ids}

            assert first_ids == ids, "first claim must pick up all seeded events"
            assert second_ids == set(), "second claim must not re-return claimed events"
        finally:
            _delete_agent_events(repo, ids)

    def test_claimed_events_recoverable_as_stale(self):
        from agent.data.models import AgentEvent, AgentEventType, EventStatus
        from agent.agents.event_router import get_event_dispatcher
        repo = get_repository()
        now = datetime.now(timezone.utc)
        ev = AgentEvent(
            event_id=f"evt_stale_{RUN_TAG}", event_type=AgentEventType.NEED_CREATED,
            status=EventStatus.PENDING, created_at=now.isoformat(),
            metadata={}, organization_id=None,
        )
        repo.append_agent_event(ev)
        try:
            claimed = repo.claim_pending_agent_events(limit=10000)
            assert any(e.event_id == ev.event_id for e in claimed)

            dispatcher = get_event_dispatcher()
            dispatcher.recover_stale_events(repo=repo, stale_threshold_seconds=0)
            recovered = repo.get_agent_event(ev.event_id)
            assert recovered.status == EventStatus.PENDING.value
        finally:
            _delete_agent_events(repo, {ev.event_id})

    @pytest.mark.skipif(
        os.environ.get("DATABASE_URL", "").strip() == "",
        reason="restart durability and rollback semantics are PostgreSQL-specific; "
               "InMemoryRepository is intentionally per-process by design",
    )
    def test_restart_durability(self):
        """Simulates an application restart: reset the cached repository and
        re-resolve it; previously written rows must still be there."""
        from agent.data.models import Need
        repo = get_repository()
        now = datetime.now(timezone.utc)
        need_id = f"need_dur_{RUN_TAG}"
        repo.create_need(Need(
            id=need_id, need_type="water", title="durability", district_id=None,
            lat=26.7, lon=94.2, urgency="high", status="OPEN",
            created_at=now, updated_at=now,
        ))
        reset_repository()
        repo2 = get_repository()
        assert type(repo2).__name__ == "PostgresRepository"
        assert repo2.get_need(need_id) is not None
        # Cleanup
        from agent.data.schema import needs as needs_table
        with repo2._engine.begin() as conn:
            conn.execute(needs_table.delete().where(needs_table.c.id == need_id))

    @pytest.mark.skipif(
        os.environ.get("DATABASE_URL", "").strip() == "",
        reason="transaction rollback is exercised against PostgreSQL engine semantics",
    )
    def test_failed_transaction_rolls_back(self):
        """A failed multi-statement transaction must leave no partial rows."""
        from agent.data.schema import needs as needs_table
        from sqlalchemy import insert
        repo = get_repository()
        need_id = f"need_rb_{RUN_TAG}"
        with pytest.raises(Exception):
            with repo._engine.begin() as conn:
                conn.execute(insert(needs_table).values(
                    id=need_id, need_type="water", title="rollback", description="",
                    urgency="HIGH", status="OPEN", requested_resources={},
                    reporter_type="manual", confidence=1.0, metadata={},
                ))
                raise RuntimeError("force rollback")
        assert repo.get_need(need_id) is None
