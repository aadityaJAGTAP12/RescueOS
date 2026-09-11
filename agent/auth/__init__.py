"""
ReliefOS Authentication & Authorization Module
"""

from agent.auth.models import (
    AuthenticatedPrincipal,
    OrganizationMembership,
    User,
    UserRole,
)
from agent.auth.service import (
    AuthService,
    create_session_token,
    hash_password,
    verify_password,
    verify_session_token,
)
from agent.auth.decorators import (
    get_token_from_request,
    is_auth_enforced,
    require_auth,
    require_network_operator,
    require_org_role,
    resolve_request_principal,
)

__all__ = [
    "User",
    "OrganizationMembership",
    "UserRole",
    "AuthenticatedPrincipal",
    "AuthService",
    "hash_password",
    "verify_password",
    "create_session_token",
    "verify_session_token",
    "require_auth",
    "require_org_role",
    "require_network_operator",
    "resolve_request_principal",
    "is_auth_enforced",
    "get_token_from_request",
]
