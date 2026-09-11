"""
ReliefOS Authentication & Authorization Decorators — Production Hardening

Provides `@require_auth`, `@require_org_role`, and `@require_network_operator`
decorators for Flask API endpoints with fail-closed production enforcement
and backward-compatible development fallback.
"""

from __future__ import annotations

import functools
import logging
import os
from typing import Callable, Optional

from flask import current_app, g, jsonify, request

from agent.auth.models import AuthenticatedPrincipal, UserRole

logger = logging.getLogger("reliefos.auth")

AUTH_HEADER_NAME = "Authorization"
AUTH_COOKIE_NAME = "reliefos_auth_token"


def is_auth_enforced() -> bool:
    """
    Check whether authentication is strictly enforced.
    True in production or when explicitly enabled via AUTH_ENFORCED=true.
    """
    env = os.environ.get("ENVIRONMENT", "development").lower()
    enforced = os.environ.get("AUTH_ENFORCED", "").lower() in ("true", "1", "yes")
    return env == "production" or enforced


def get_token_from_request(req) -> Optional[str]:
    """
    Extract session token from Authorization: Bearer <token> header or cookie.
    """
    auth_header = req.headers.get(AUTH_HEADER_NAME)
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return req.cookies.get(AUTH_COOKIE_NAME)


def resolve_request_principal(req) -> Optional[AuthenticatedPrincipal]:
    """
    Resolve AuthenticatedPrincipal for the current Flask request.
    Uses cached principal on `g.principal` if already resolved.
    """
    if hasattr(g, "principal") and g.principal is not None:
        return g.principal

    auth_service = getattr(current_app, "auth_service", None)
    if not auth_service:
        return None

    token = get_token_from_request(req)
    if not token:
        return None

    principal = auth_service.get_principal_from_token(token)
    g.principal = principal
    return principal


def _request_id() -> str:
    """Correlation id for security log lines, if the tracing middleware ran."""
    try:
        return getattr(g, "request_id", "-")
    except RuntimeError:
        return "-"


def require_auth(fn: Callable) -> Callable:
    """
    Decorator requiring an authenticated user.
    In production / auth-enforced mode, fails closed with 401 Unauthorized.
    In development mode without token, allows execution with a warning.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        principal = resolve_request_principal(request)
        if principal:
            g.current_user = principal.user
            return fn(*args, **kwargs)

        if is_auth_enforced():
            logger.warning(
                "[RequestID: %s] auth denied: unauthenticated request to %s %s",
                _request_id(), request.method, request.path,
            )
            return jsonify({
                "error": "Authentication required",
                "code": "UNAUTHORIZED",
            }), 401

        # Dev / Test fallback: Proceed without strict auth
        logger.debug(f"Allowing unauthenticated request to {request.path} (auth not strictly enforced)")
        return fn(*args, **kwargs)

    return wrapper


def require_org_role(min_role: UserRole | str = UserRole.ORG_VIEWER) -> Callable:
    """
    Decorator requiring the user to have at least `min_role` in the target organization.
    The target organization is determined via `resolve_current_org(request)`.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            from agent.org_context import resolve_current_org
            target_org_id = resolve_current_org(request)

            principal = resolve_request_principal(request)
            if principal:
                g.current_user = principal.user
                if principal.has_org_access(target_org_id, min_role):
                    return fn(*args, **kwargs)

                # Authenticated but insufficient permissions
                if is_auth_enforced():
                    logger.warning(
                        "[RequestID: %s] authz denied: user=%s lacks %s for org=%s at %s %s",
                        _request_id(), principal.user_id,
                        min_role.value if isinstance(min_role, UserRole) else str(min_role),
                        target_org_id, request.method, request.path,
                    )
                    return jsonify({
                        "error": f"Insufficient permissions for organization '{target_org_id}'",
                        "code": "FORBIDDEN",
                        "required_role": min_role.value if isinstance(min_role, UserRole) else str(min_role),
                    }), 403

            if is_auth_enforced():
                logger.warning(
                    "[RequestID: %s] auth denied: unauthenticated request to %s %s",
                    _request_id(), request.method, request.path,
                )
                return jsonify({
                    "error": "Authentication required",
                    "code": "UNAUTHORIZED",
                }), 401

            # Dev / Test fallback
            return fn(*args, **kwargs)

        return wrapper
    return decorator


def require_network_operator(fn: Callable) -> Callable:
    """
    Decorator requiring NETWORK_OPERATOR role.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        principal = resolve_request_principal(request)
        if principal:
            g.current_user = principal.user
            if principal.is_network_operator:
                return fn(*args, **kwargs)

            if is_auth_enforced():
                logger.warning(
                    "[RequestID: %s] authz denied: user=%s lacks NETWORK_OPERATOR at %s %s",
                    _request_id(), principal.user_id, request.method, request.path,
                )
                return jsonify({
                    "error": "Network Operator role required",
                    "code": "FORBIDDEN",
                }), 403

        if is_auth_enforced():
            logger.warning(
                "[RequestID: %s] auth denied: unauthenticated request to %s %s",
                _request_id(), request.method, request.path,
            )
            return jsonify({
                "error": "Authentication required",
                "code": "UNAUTHORIZED",
            }), 401

        # Dev / Test fallback
        return fn(*args, **kwargs)

    return wrapper
