"""
Organization identity seam tests — Phase 7I (org context)

Proves structurally that multi-org separation works through the identity
seam, WITHOUT claiming any security enforcement:

1. resolve_current_org resolves the session cookie, falls back to the
   default org when absent.
2. POST /api/session/org selects an org; GET /api/session/org reports it.
3. Private resource/team/mission endpoints, NGO agent analysis, and
   publish-offer all resolve to the SELECTED org's data — not to any
   org id supplied by the client.
4. Trust boundary: a client attempting to pass a different org_id in the
   request body does NOT get honored — the session-derived context wins.
5. Switching context between two real organizations isolates their
   private state (org A's data is invisible while acting as org B).

NOTE: this is identity/context separation, not authentication. Any client
can select any org by setting the cookie; there is deliberately no
password or credential anywhere in this flow.

DB-safety (Item 5B): this file does NOT force RELIEFOS_MEMORY — repository
selection is resolved explicitly by tests/conftest.py and asserted there,
so the suite runs identically against InMemoryRepository and real
PostgreSQL. All org ids are unique per run (never the production
org_alpha/org_beta) and every run's footprint is cleaned up before and
after each test:
  - shared-network rows (organizations, resource_offers, needs) are
    deleted from the repository when PostgreSQL is active;
  - the private workspace is FILE-backed (data/orgs/<org_id>/*.json) and
    its dedicated org dirs are removed.
Production authorization semantics are untouched — cleanup happens at the
data layer only.
"""

import json
import os
import shutil
import uuid

import pytest

from agent.data.repository import get_repository, reset_repository
from agent.org_context import (
    SESSION_COOKIE_NAME,
    DEFAULT_ORG_ID,
    resolve_current_org,
)

# Unique per-run org ids: never collide with production data
# (org_alpha/org_beta) in either the file-backed workspace or the DB.
RUN_TAG = uuid.uuid4().hex[:8]

def _oid(base: str) -> str:
    return f"org_ctx_{base}_{RUN_TAG}"

A_ORG = _oid("alpha")     # was org_alpha
B_ORG = _oid("beta")      # was org_beta
E_ORG = _oid("evil")      # was org_evil
NEED_ID = f"need_ctx_{RUN_TAG}"

_ORGS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "orgs",
)

# Offers created by the cookieless default-org tests (server-side ids);
# deleted by id in the cleanup fixture.
_DEFAULT_ORG_OFFER_IDS: set = set()


def _purge_file_state():
    for org in (A_ORG, B_ORG, E_ORG):
        shutil.rmtree(os.path.join(_ORGS_DIR, org), ignore_errors=True)


def _purge_db_rows():
    """In PostgreSQL mode, delete this run's shared-network rows before AND
    after each test. Targeted to this run's unique ids — production data is
    never touched. Private resources/teams/missions are file-backed and
    covered by _purge_file_state."""
    if os.environ.get("RELIEFOS_MEMORY", "").strip() in ("1", "true", "yes"):
        return
    if not os.environ.get("DATABASE_URL", "").strip():
        return
    from agent.data.repository import get_repository
    from agent.data.schema import (
        coordination_proposals, organizations, needs, resource_offers,
    )
    repo = get_repository()
    assert type(repo).__name__ == "PostgresRepository", (
        "DATABASE_URL is set but repository is not PostgresRepository — "
        "DB-mode run would silently test the wrong backend"
    )
    with repo._engine.begin() as conn:
        conn.execute(coordination_proposals.delete().where(
            coordination_proposals.c.organization_id.in_([A_ORG, B_ORG, E_ORG])
        ))
        conn.execute(resource_offers.delete().where(
            resource_offers.c.organization_id.in_([A_ORG, B_ORG, E_ORG])
        ))
        if _DEFAULT_ORG_OFFER_IDS:
            conn.execute(resource_offers.delete().where(
                resource_offers.c.id.in_(list(_DEFAULT_ORG_OFFER_IDS))
            ))
        conn.execute(needs.delete().where(needs.c.id == NEED_ID))
        conn.execute(organizations.delete().where(
            organizations.c.id.in_([A_ORG, B_ORG, E_ORG])
        ))


@pytest.fixture(autouse=True)
def fresh_repo():
    reset_repository()
    repo = get_repository()
    _purge_file_state()
    _purge_db_rows()
    yield repo
    _purge_file_state()
    _purge_db_rows()
    _DEFAULT_ORG_OFFER_IDS.clear()
    reset_repository()


@pytest.fixture
def client():
    from agent.api import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _create_org(client, org_id, name):
    resp = client.post(
        "/api/organizations",
        json={"id": org_id, "name": name, "organization_type": "ngo"},
    )
    assert resp.status_code == 201, resp.get_json()


def _select_org(client, org_id):
    resp = client.post("/api/session/org", json={"org_id": org_id})
    assert resp.status_code == 200, resp.get_json()
    return resp


def _seed_private_state(client, org_id, tag=None):
    """Seed distinguishable private state while acting as org_id.

    Returns the unique tag used, so assertions can identify this run's items
    even though the file-backed store persists across runs.
    """
    tag = tag or f"tag{uuid.uuid4().hex[:8]}"
    _select_org(client, org_id)
    r = client.post(
        "/api/my-org/resources",
        json={"resource_type": f"widget_{tag}", "quantity": 7, "unit": "units"},
    )
    assert r.status_code == 201, r.get_json()
    t = client.post("/api/my-org/teams", json={"name": f"Team {tag}"})
    assert t.status_code == 201, t.get_json()
    m = client.post("/api/my-org/missions", json={"name": f"Mission {tag}"})
    assert m.status_code == 201, m.get_json()
    return tag


# ---------------------------------------------------------------------------
# 1. resolve_current_org unit behavior
# ---------------------------------------------------------------------------

class TestResolveCurrentOrg:
    def test_falls_back_to_default_without_cookie(self):
        class FakeRequest:
            cookies = {}

        assert resolve_current_org(FakeRequest()) == DEFAULT_ORG_ID

    def test_resolves_cookie_value(self):
        class FakeRequest:
            cookies = {SESSION_COOKIE_NAME: "org_custom"}

        assert resolve_current_org(FakeRequest()) == "org_custom"

    def test_blank_cookie_falls_back_to_default(self):
        class FakeRequest:
            cookies = {SESSION_COOKIE_NAME: "   "}

        assert resolve_current_org(FakeRequest()) == DEFAULT_ORG_ID


# ---------------------------------------------------------------------------
# 2. Session org selection endpoints
# ---------------------------------------------------------------------------

class TestSessionOrgEndpoints:
    def test_get_session_org_default(self, client):
        data = client.get("/api/session/org").get_json()
        assert data["org_id"] == DEFAULT_ORG_ID

    def test_set_then_get_session_org(self, client):
        _create_org(client, A_ORG, "Alpha NGO")
        resp = _select_org(client, A_ORG)
        assert resp.headers.get("Set-Cookie") is not None

        data = client.get("/api/session/org").get_json()
        assert data["org_id"] == A_ORG
        assert data["registered"] is True

    def test_set_session_org_unknown_org_rejected(self, client):
        resp = client.post("/api/session/org", json={"org_id": _oid("missing")})
        assert resp.status_code == 404

    def test_set_session_org_requires_org_id(self, client):
        resp = client.post("/api/session/org", json={})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 3. Org switching isolates private state end-to-end
# ---------------------------------------------------------------------------

class TestOrgSwitchingIsolation:
    def test_private_endpoints_follow_selected_org(self, client):
        _create_org(client, A_ORG, "Alpha NGO")
        _create_org(client, B_ORG, "Beta NGO")

        tag_a = _seed_private_state(client, A_ORG)
        tag_b = _seed_private_state(client, B_ORG)

        # Acting as A: this run's items visible, B's tagged items not
        _select_org(client, A_ORG)
        resources = client.get("/api/my-org/resources").get_json()["resources"]
        teams = client.get("/api/my-org/teams").get_json()["teams"]
        missions = client.get("/api/my-org/missions").get_json()["missions"]
        assert all(r["org_id"] == A_ORG for r in resources)
        assert any(r["resource_type"] == f"widget_{tag_a}" for r in resources)
        assert not any(r["resource_type"] == f"widget_{tag_b}" for r in resources)
        assert any(t["name"] == f"Team {tag_a}" for t in teams)
        assert not any(t["name"] == f"Team {tag_b}" for t in teams)
        assert any(m["name"] == f"Mission {tag_a}" for m in missions)
        assert not any(m["name"] == f"Mission {tag_b}" for m in missions)

        # Switch to B — A's private data must be invisible
        _select_org(client, B_ORG)
        resources = client.get("/api/my-org/resources").get_json()["resources"]
        teams = client.get("/api/my-org/teams").get_json()["teams"]
        missions = client.get("/api/my-org/missions").get_json()["missions"]
        assert all(r["org_id"] == B_ORG for r in resources)
        assert any(r["resource_type"] == f"widget_{tag_b}" for r in resources)
        assert not any(r["resource_type"] == f"widget_{tag_a}" for r in resources)
        assert any(t["name"] == f"Team {tag_b}" for t in teams)
        assert not any(t["name"] == f"Team {tag_a}" for t in teams)
        assert any(m["name"] == f"Mission {tag_b}" for m in missions)
        assert not any(m["name"] == f"Mission {tag_a}" for m in missions)

        # And the summary endpoint reports the selected org
        summary = client.get("/api/my-org/summary").get_json()
        assert summary["org_id"] == B_ORG

    def test_publish_offer_uses_selected_org(self, client):
        _create_org(client, A_ORG, "Alpha NGO")
        _create_org(client, B_ORG, "Beta NGO")
        _select_org(client, A_ORG)

        resp = client.post(
            "/api/my-org/publish-offer",
            json={"resource_type": "boat", "quantity": 2, "unit": "units"},
        )
        assert resp.status_code == 201, resp.get_json()
        offer = resp.get_json()["offer"]
        assert offer["organization_id"] == A_ORG

        offers = client.get(
            f"/api/offers?organization_id={A_ORG}"
        ).get_json()["offers"]
        assert any(o["id"] == offer["id"] for o in offers)

    def test_ngo_agent_analysis_uses_selected_org(self, client):
        _create_org(client, A_ORG, "Alpha NGO")
        _create_org(client, B_ORG, "Beta NGO")
        tag_a = _seed_private_state(client, A_ORG)
        _seed_private_state(client, B_ORG)
        _select_org(client, A_ORG)

        resource_type = f"widget_{tag_a}"  # only A holds this type
        need = {
            "id": NEED_ID,
            "need_type": resource_type,
            "title": "Widgets needed",
            "urgency": "high",
            "requested_resources": [
                {"resource_type": resource_type, "quantity": 1, "unit": "units"}
            ],
        }
        resp = client.post("/api/my-org/agent/analyze-need", json={"need": need})
        assert resp.status_code == 200, resp.get_json()
        result = resp.get_json()
        # A holds the tagged resource type (7 units, seeded above), so the
        # analysis must reflect A's private inventory. B's tagged items
        # must never appear. (The analysis body does not embed the org id;
        # the tagged resource type can only come from A's private store.)
        blob = json.dumps(result)
        assert f"widget_{tag_a}" in blob
        assert B_ORG not in blob
        # The proposed publication (if any) must name the selected org.
        if result.get("proposed_publication"):
            assert result["proposed_publication"].get("organization_id", A_ORG) == A_ORG

    def test_situation_endpoint_reports_selected_org(self, client):
        _create_org(client, B_ORG, "Beta NGO")
        _select_org(client, B_ORG)
        situation = client.get("/api/my-org/agent/situation").get_json()
        assert situation["org_id"] == B_ORG


# ---------------------------------------------------------------------------
# 4. Trust boundary: client-supplied org_id is ignored
# ---------------------------------------------------------------------------

class TestTrustBoundary:
    def test_publish_offer_ignores_client_org_id(self, client):
        """A body org_id different from the session context must NOT win."""
        _create_org(client, A_ORG, "Alpha NGO")
        _create_org(client, E_ORG, "Evil Impersonator")
        _select_org(client, A_ORG)

        resp = client.post(
            "/api/my-org/publish-offer",
            json={
                "resource_type": "boat",
                "quantity": 5,
                "unit": "units",
                "organization_id": E_ORG,  # attacker-supplied
                "organization_name": "Evil Impersonator",
            },
        )
        assert resp.status_code == 201, resp.get_json()
        offer = resp.get_json()["offer"]
        # Server-derived context wins:
        assert offer["organization_id"] == A_ORG
        assert offer["organization_id"] != E_ORG

        # No offer was recorded for the attacker org.
        evil_offers = client.get(
            f"/api/offers?organization_id={E_ORG}"
        ).get_json()["offers"]
        assert evil_offers == []

    def test_legacy_offers_post_ignores_client_org_id(self, client):
        """POST /api/offers must also derive the org from the session."""
        _create_org(client, A_ORG, "Alpha NGO")
        _create_org(client, E_ORG, "Evil Impersonator")
        _select_org(client, A_ORG)

        resp = client.post(
            "/api/offers",
            json={
                "resource_type": "water",
                "quantity": 10,
                "unit": "liters",
                "organization_id": E_ORG,  # attacker-supplied
            },
        )
        assert resp.status_code == 201, resp.get_json()
        assert resp.get_json()["offer"]["organization_id"] == A_ORG

    def test_private_endpoints_have_no_client_org_input(self, client):
        """Private endpoints expose no way to name another org."""
        _create_org(client, A_ORG, "Alpha NGO")
        _select_org(client, A_ORG)
        # Even stuffing an org_id field into the payload changes nothing:
        resp = client.post(
            "/api/my-org/resources",
            json={
                "resource_type": "boat",
                "quantity": 1,
                "unit": "units",
                "org_id": E_ORG,
                "organization_id": E_ORG,
            },
        )
        assert resp.status_code == 201
        resource = resp.get_json()["resource"]
        assert resource["org_id"] == A_ORG

    def test_old_org_scoped_routes_are_gone(self, client):
        """/api/orgs/<org_id>/... trusted client-supplied org ids; they must 404."""
        for path in (
            f"/api/orgs/{_oid('demo')}/summary",
            f"/api/orgs/{_oid('demo')}/resources",
            f"/api/orgs/{_oid('demo')}/teams",
            f"/api/orgs/{_oid('demo')}/missions",
            f"/api/orgs/{_oid('demo')}/publish-offer",
        ):
            resp = client.get(path)
            if resp.status_code == 405:
                # Method not allowed is fine (route gone, method mismatch)
                continue
            assert resp.status_code == 404, f"{path} -> {resp.status_code}"


# ---------------------------------------------------------------------------
# 5. Cookieless callers keep working (tools/diagnostics)
# ---------------------------------------------------------------------------

class TestCookielessFallback:
    def test_my_org_without_cookie_uses_default_org(self, client):
        # The default org may not exist in a fresh repo — the endpoint still
        # resolves to the default org id rather than erroring.
        resp = client.get("/api/my-org/resources")
        assert resp.status_code == 200
        assert "resources" in resp.get_json()

    def test_publish_offer_cookieless_creates_default_org(self, client):
        resp = client.post(
            "/api/my-org/publish-offer",
            json={"resource_type": "boat", "quantity": 1, "unit": "units"},
        )
        assert resp.status_code == 201
        offer = resp.get_json()["offer"]
        assert offer["organization_id"] == DEFAULT_ORG_ID
        # Track the offer id so the cleanup fixture can remove it from the
        # durable store in PostgreSQL mode.
        _DEFAULT_ORG_OFFER_IDS.add(offer["id"])
