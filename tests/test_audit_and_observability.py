"""
ReliefOS Production Hardening — Audit Logging & Observability Test Suite

Tests structured audit logging of consequential actions, actor attribution,
request correlation ID tracing, and pagination of audit trails.
"""

import pytest

from agent.audit.models import AuditLog
from agent.audit.service import record_audit_log
from agent.auth.models import User, UserRole
from agent.auth.service import AuthService
from agent.data.repository import InMemoryRepository
from agent.api import app


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def auth_service(repo):
    return AuthService(repository=repo, secret_key="test-observability-secret-key-32ch")


@pytest.fixture
def client(auth_service):
    app.config["TESTING"] = True
    app.auth_service = auth_service
    with app.test_client() as c:
        yield c


class TestConsequentialActionAuditLogging:
    def test_record_and_list_audit_logs(self, repo):
        # Create an audit log for an approved proposal
        log1 = record_audit_log(
            repository=repo,
            action="approve_proposal",
            entity_type="proposal",
            entity_id="prop_123",
            actor_id="usr_admin",
            organization_id="org_redcross",
            from_state="EVALUATED",
            to_state="CONFIRMED",
            details={"offer_id": "off_456"},
        )
        assert log1.id is not None
        assert log1.action == "approve_proposal"

        # Create another log
        record_audit_log(
            repository=repo,
            action="publish_offer",
            entity_type="offer",
            entity_id="off_456",
            actor_id="usr_admin",
            organization_id="org_redcross",
            to_state="OFFERED",
        )

        # List with filters
        all_logs = repo.list_audit_logs()
        assert len(all_logs) == 2

        proposal_logs = repo.list_audit_logs(entity_type="proposal")
        assert len(proposal_logs) == 1
        assert proposal_logs[0].entity_id == "prop_123"

        org_logs = repo.list_audit_logs(organization_id="org_redcross")
        assert len(org_logs) == 2

    def test_audit_log_api_endpoint(self, client):
        import time
        from agent.data.repository import get_repository
        active_repo = get_repository()
        auth_svc = AuthService(repository=active_repo, secret_key="test-observability-secret-key-32ch")
        app.auth_service = auth_svc

        # Create an authenticated user with unique username
        uid = int(time.time() * 1000)
        user, _ = auth_svc.register_user(
            username=f"auditor_{uid}",
            password="StrongPassword123!",
            email=f"auditor_{uid}@reliefos.org",
        )
        token = auth_svc.create_token_for_user(user)

        # Seed audit entries
        record_audit_log(active_repo, action="apply_override", entity_type="override", entity_id=f"ovr_{uid}", actor_id=user.id)

        # Query API with auth header
        resp = client.get("/api/audit/logs", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] >= 1
        assert any(l["action"] == "apply_override" for l in data["logs"])


class TestRequestCorrelationAndTracing:
    def test_request_id_injected_and_propagated(self, client):
        custom_id = "trace-correlation-id-9988"
        resp = client.get("/api/health/liveness", headers={"X-Request-ID": custom_id})
        assert resp.status_code == 200
        assert resp.headers.get("X-Request-ID") == custom_id

    def test_automatic_request_id_generated_when_missing(self, client):
        resp = client.get("/api/health/liveness")
        assert resp.status_code == 200
        gen_id = resp.headers.get("X-Request-ID")
        assert gen_id is not None
        assert gen_id.startswith("req_")
