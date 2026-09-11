"""
ReliefOS Organization Identity Seam — "which organization is this?"

This module is the SINGLE SOURCE every piece of NGO / private-workspace
logic uses to determine the organization a request belongs to. Backend
handlers must never read an org id from the request body, query string,
or URL path for org-scoped actions; they call `resolve_current_org(request)`.

┌─────────────────────────────────────────────────────────────────────────┐
│ *** THIS IS IDENTITY / CONTEXT ONLY — IT IS NOT AUTHENTICATION ***      │
│                                                                         │
│ - There is NO password, login, session token, or credential of any     │
│   kind. Anyone can select ANY organization from the picker (or via     │
│   POST /api/session/org) and immediately act as that organization.     │
│ - The cookie is a plain, unsigned, client-visible preference. It       │
│   carries zero security value and can be freely forged.                │
│ - As-is, this is NOT safe for any multi-tenant or public deployment.   │
│ - Real authentication/authorization is deliberately deferred to a      │
│   specific future deployment's needs. The value built here is the      │
│   seam: every org-scoped code path already flows through ONE           │
│   function, so a future auth layer only has to change that function    │
│   (e.g. derive org_id from a verified identity) — no endpoint          │
│   changes required.                                                    │
└─────────────────────────────────────────────────────────────────────────┘

Mechanism (deliberately minimal):
  1. The org-selection UI (frontend OrgSwitcher) calls POST /api/session/org
     with a chosen (existing or just-created) organization id.
  2. That endpoint validates the organization exists, then stores the
     choice in a plain cookie (`reliefos_org_id`).
  3. `resolve_current_org(request)` reads that cookie per request. If it is
     absent/blank it falls back to DEFAULT_ORG_ID so cookieless callers
     (diagnostic tools, curl, tests) keep working against a known org.

Validation policy: the seam itself does NOT verify that the cookie's org
is registered (private workspace storage is file-backed and creates
directories on demand). Registration is validated at switch time in
POST /api/session/org — the only place the cookie is ever written.
"""

from __future__ import annotations

from flask import Response

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Name of the plain preference cookie holding the selected organization id.
SESSION_COOKIE_NAME = "reliefos_org_id"

# Fallback organization when no selection cookie is present. This is the
# historical demo org (its private workspace files live in data/orgs/org_demo/),
# so cookieless API callers keep resolving to the same org as before the seam.
DEFAULT_ORG_ID = "org_demo"

# 30 days — it is a UI preference, not a credential; lifetime is arbitrary.
COOKIE_MAX_AGE_SECONDS = 30 * 24 * 3600


# ---------------------------------------------------------------------------
# The seam
# ---------------------------------------------------------------------------

def resolve_current_org(req) -> str:
    """Resolve the organization context for a request.

    Resolution order:
      1. If an authenticated principal exists:
         a. If a valid `reliefos_org_id` cookie is present and the user has access
            to it (or is a NETWORK_OPERATOR), use that org.
         b. Otherwise, default to the user's primary/first organization membership.
      2. If no authenticated principal (or in dev/test mode):
         a. The `reliefos_org_id` cookie (set by POST /api/session/org).
         b. DEFAULT_ORG_ID ("org_demo") for cookieless callers.

    Args:
        req: Flask request object.

    Returns:
        The organization id string for this request's org context.
    """
    from agent.auth.decorators import is_auth_enforced

    cookie_org = (req.cookies.get(SESSION_COOKIE_NAME) or "").strip()

    principal = None
    try:
        from flask import g
        principal = getattr(g, "principal", None)
        if principal is None:
            from agent.auth.decorators import resolve_request_principal
            principal = resolve_request_principal(req)
    except RuntimeError:
        # No Flask request/app context (unit tests, diagnostic tools) — the
        # cookie seam still works below, exactly as before hardening.
        principal = None
    except Exception:
        # Token/service failure must NOT silently fall back to demo mode when
        # auth is enforced. Resolve enforcement outside the try so a broken
        # resolver can only widen access in development, never in production.
        principal = None
        if is_auth_enforced():
            raise

    if principal:
        if cookie_org and (principal.is_network_operator or principal.get_role_for_org(cookie_org)):
            return cookie_org
        if principal.memberships:
            return principal.memberships[0].organization_id
        # Authenticated user with no matching membership for the cookie and
        # no memberships at all: the cookie alone must never select an org
        # the identity has no relationship with. In enforced mode this fails
        # closed (empty context); dev/test keeps the lenient behavior.
        if cookie_org and not is_auth_enforced():
            return cookie_org
        if is_auth_enforced():
            return ""

    if cookie_org:
        return cookie_org

    # Fail closed: in enforced (production) mode an unauthenticated request
    # must never resolve to the demo organization. Public endpoints that
    # need no org context simply get an empty one.
    if is_auth_enforced():
        return ""

    return DEFAULT_ORG_ID


# ---------------------------------------------------------------------------
# Cookie write helper (used only by the /api/session/org endpoints)
# ---------------------------------------------------------------------------

def set_current_org_cookie(resp: Response, org_id: str) -> Response:
    """Stamp the org-selection cookie onto a response.

    Callers MUST validate that `org_id` refers to an existing organization
    before invoking this (POST /api/session/org does). Kept here so the
    cookie name/lifetime live in one place alongside the seam.
    """
    resp.set_cookie(
        SESSION_COOKIE_NAME,
        org_id,
        max_age=COOKIE_MAX_AGE_SECONDS,
        samesite="Lax",
    )
    return resp
