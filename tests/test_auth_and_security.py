"""
ReliefOS Production Hardening — Authentication & Security Test Suite

Tests password hashing, token validation, role-based access control,
security headers, production error sanitization, and input validators.
"""

import os
import time
import pytest
from unittest.mock import patch

from agent.auth.models import AuthenticatedPrincipal, OrganizationMembership, User, UserRole
from agent.auth.service import (
    AuthService,
    create_session_token,
    hash_password,
    verify_password,
    verify_session_token,
)
from agent.data.repository import InMemoryRepository
from agent.validation.validators import (
    ValidationError,
    sanitize_sensitive_data,
    validate_coordinates,
    validate_id,
    validate_pagination,
    validate_status_transition,
    validate_string,
)
from agent.api import app


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def auth_service(repo):
    return AuthService(repository=repo, secret_key="test-secret-key-12345678901234567890")


@pytest.fixture
def client(auth_service):
    app.config["TESTING"] = True
    app.auth_service = auth_service
    with app.test_client() as c:
        yield c


class TestPasswordAndTokenSecurity:
    def test_password_hashing_and_verification(self):
        pw = "SuperSecret123!"
        hashed = hash_password(pw)

        assert hashed.startswith("pbkdf2:sha256:600000$")
        assert verify_password(pw, hashed) is True
        assert verify_password("WrongPassword", hashed) is False
        assert verify_password("", hashed) is False
        assert verify_password(pw, "") is False

    def test_hash_uniqueness_with_salt(self):
        pw = "SamePassword"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert h1 != h2  # Different salts
        assert verify_password(pw, h1) is True
        assert verify_password(pw, h2) is True

    def test_session_token_creation_and_verification(self):
        secret = "secret-key-32-chars-long-1234567890"
        token = create_session_token("usr_123", "responder_bob", secret_key=secret, expires_in_seconds=3600)

        payload = verify_session_token(token, secret)
        assert payload is not None
        assert payload["sub"] == "usr_123"
        assert payload["username"] == "responder_bob"

    def test_session_token_tamper_evidence(self):
        secret = "secret-key-32-chars-long-1234567890"
        token = create_session_token("usr_123", "responder_bob", secret_key=secret)
        parts = token.split(".")
        # Tamper payload
        tampered_token = f"{parts[0]}.eyJhZG1pbiI6dHJ1ZX0.{parts[2]}"
        assert verify_session_token(tampered_token, secret) is None

    def test_session_token_expiration(self):
        secret = "secret-key-32-chars-long-1234567890"
        token = create_session_token("usr_123", "bob", secret_key=secret, expires_in_seconds=-10)
        assert verify_session_token(token, secret) is None


class TestRoleHierarchyAndPrincipals:
    def test_role_hierarchy_permissions(self):
        # Network operator has access to everything
        assert UserRole.has_sufficient_role(UserRole.NETWORK_OPERATOR, UserRole.ORG_ADMIN) is True
        assert UserRole.has_sufficient_role(UserRole.NETWORK_OPERATOR, UserRole.ORG_VIEWER) is True

        # Org Admin > Org Operator > Org Viewer
        assert UserRole.has_sufficient_role(UserRole.ORG_ADMIN, UserRole.ORG_OPERATOR) is True
        assert UserRole.has_sufficient_role(UserRole.ORG_ADMIN, UserRole.ORG_VIEWER) is True
        assert UserRole.has_sufficient_role(UserRole.ORG_OPERATOR, UserRole.ORG_VIEWER) is True
        assert UserRole.has_sufficient_role(UserRole.ORG_VIEWER, UserRole.ORG_OPERATOR) is False
        assert UserRole.has_sufficient_role(UserRole.ORG_OPERATOR, UserRole.ORG_ADMIN) is False

    def test_authenticated_principal_org_access(self, auth_service):
        user, mem = auth_service.register_user(
            username="alice_redcross",
            email="alice@redcross.org",
            password="SecurePassword999!",
            initial_org_id="org_redcross",
            initial_role=UserRole.ORG_OPERATOR,
        )
        principal = auth_service.get_principal(user.id)
        assert principal is not None
        assert principal.has_org_access("org_redcross", UserRole.ORG_OPERATOR) is True
        assert principal.has_org_access("org_redcross", UserRole.ORG_ADMIN) is False
        assert principal.has_org_access("org_other", UserRole.ORG_VIEWER) is False


class TestInputValidationAndSanitization:
    def test_validate_id(self):
        assert validate_id("usr_12345") == "usr_12345"
        assert validate_id("org-demo_1") == "org-demo_1"
        with pytest.raises(ValidationError):
            validate_id("invalid id with spaces")
        with pytest.raises(ValidationError):
            validate_id("drop table users; --")

    def test_validate_coordinates(self):
        lat, lng = validate_coordinates("26.9894", "94.6698")
        assert lat == 26.9894
        assert lng == 94.6698
        with pytest.raises(ValidationError):
            validate_coordinates(95.0, 50.0)  # Lat out of range
        with pytest.raises(ValidationError):
            validate_coordinates(20.0, -190.0)  # Lng out of range
        with pytest.raises(ValidationError):
            validate_coordinates("invalid", "coords")

    def test_validate_pagination(self):
        limit, offset = validate_pagination("25", "10")
        assert limit == 25
        assert offset == 10

        limit, offset = validate_pagination("-5", "-2")
        assert limit == 50
        assert offset == 0

        limit, offset = validate_pagination("5000", "0", max_limit=100)
        assert limit == 100

    def test_sanitize_sensitive_data(self):
        payload = {
            "username": "operator1",
            "password": "ClearTextPassword!",
            "token": "secret-session-token",
            "nested": {
                "api_key": "private-key-value",
                "normal_field": "visible",
            },
        }
        sanitized = sanitize_sensitive_data(payload)
        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["token"] == "[REDACTED]"
        assert sanitized["nested"]["api_key"] == "[REDACTED]"
        assert sanitized["nested"]["normal_field"] == "visible"


class TestSecurityMiddlewareAndHeaders:
    def test_security_headers_present_on_responses(self, client):
        resp = client.get("/api/health/liveness")
        assert resp.status_code == 200
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
        assert resp.headers.get("Content-Security-Policy") is not None
        assert resp.headers.get("X-Request-ID") is not None

    def test_production_error_sanitization(self, client):
        def error_view():
            raise RuntimeError("Database connection string exposed credentials!")

        original = app.view_functions.get("api_health_liveness")
        try:
            app.view_functions["api_health_liveness"] = error_view
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                resp = client.get("/api/health/liveness")
                assert resp.status_code == 500
                data = resp.get_json()
                assert "Database connection string exposed credentials!" not in str(data)
                assert data["error"] == "Internal Server Error"
                assert "request_id" in data
        finally:
            if original:
                app.view_functions["api_health_liveness"] = original
