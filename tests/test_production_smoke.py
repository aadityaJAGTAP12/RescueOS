"""
ReliefOS Production Hardening — Production Smoke Test & End-to-End Flow

Tests end-to-end readiness checks, configuration validation, user registration/login,
protected endpoint authentication, proposal actions, and health probes.
"""

import os
import pytest
from unittest.mock import patch

from agent.config import Settings
from agent.auth.models import UserRole
from agent.auth.service import AuthService
from agent.data.repository import InMemoryRepository
from agent.api import app


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def auth_service(repo):
    return AuthService(repository=repo, secret_key="test-smoke-secret-key-at-least-32-chars-long")


@pytest.fixture
def client(auth_service):
    app.config["TESTING"] = True
    app.auth_service = auth_service
    with app.test_client() as c:
        yield c


class TestProductionReadinessConfiguration:
    def test_settings_validation_in_dev(self):
        settings = Settings(environment="development")
        errors = settings.validate_production_readiness()
        assert len(errors) == 0  # In development, default settings are fine

    def test_settings_validation_in_production_fails_on_insecure_defaults(self):
        settings = Settings(
            environment="production",
            database_url=None,  # missing postgres
            secret_key="reliefos-default-secret-key-change-in-prod",  # default insecure
            auth_enforced=False,  # missing auth enforcement
        )
        errors = settings.validate_production_readiness()
        assert len(errors) == 3
        assert any("PostgreSQL" in e for e in errors)
        assert any("RELIEFOS_SECRET_KEY" in e for e in errors)
        assert any("AUTH_ENFORCED" in e for e in errors)

    def test_settings_validation_in_production_passes_when_configured(self):
        settings = Settings(
            environment="production",
            database_url="postgresql://user:pass@db:5432/reliefos",
            secret_key="a-very-secure-random-production-secret-key-here",
            auth_enforced=True,
        )
        errors = settings.validate_production_readiness()
        assert len(errors) == 0


class TestEndToEndProductionSmokeFlow:
    def test_health_endpoints(self, client):
        resp_live = client.get("/api/health/liveness")
        assert resp_live.status_code == 200
        assert resp_live.get_json()["status"] == "alive"

        resp_ready = client.get("/api/health/readiness")
        assert resp_ready.status_code == 200
        assert resp_ready.get_json()["status"] == "ready"

    def test_auth_registration_login_and_me_flow(self, client):
        import time
        uid = int(time.time() * 1000)
        username = f"lead_coordinator_{uid}"
        email = f"lead_{uid}@reliefos.org"
        # 1. Register
        reg_payload = {
            "username": username,
            "password": "StrongPassword2026!",
            "email": email,
            "full_name": "Lead Coordinator",
            "initial_org_id": "org_disaster_cell",
            "initial_role": UserRole.ORG_ADMIN.value,
        }
        reg_resp = client.post("/api/auth/register", json=reg_payload)
        assert reg_resp.status_code == 201
        reg_data = reg_resp.get_json()
        token = reg_data["token"]
        assert token is not None
        assert reg_data["user"]["username"] == username

        # 2. Get /api/auth/me
        me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200
        me_data = me_resp.get_json()
        assert me_data["authenticated"] is True
        assert me_data["user"]["username"] == username
        assert len(me_data["memberships"]) == 1
        assert me_data["memberships"][0]["organization_id"] == "org_disaster_cell"

        # 3. Login
        login_payload = {
            "username": username,
            "password": "StrongPassword2026!",
        }
        login_resp = client.post("/api/auth/login", json=login_payload)
        assert login_resp.status_code == 200
        login_data = login_resp.get_json()
        assert login_data["token"] is not None

        # 4. Logout
        logout_resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert logout_resp.status_code == 200
        assert logout_resp.get_json()["status"] == "logged_out"
