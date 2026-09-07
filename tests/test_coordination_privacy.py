"""
Coordination Proposal Privacy Boundary Tests — Item #5, Step 1

Adversarial tests proving the Network ↔ NGO privacy boundary around
coordination proposals. Two real organizations with unmistakable private
values (SECRET_A_* / SECRET_B_*) so accidental leakage is easy to detect.

Secret-marker design:
  - SECRET strings live ONLY in private-only fields (private resource
    types/locations, private team/mission names). Published offers use the
    public type "rescue_boat", so a secret string in any public payload is
    an unambiguous leak.
  - A holds 3 private resources, B holds 2 — the stored evaluation's
    resource_assessment.total_resources proves WHICH private store was read
    (3 = A's, 2 = B's), without needing secret strings in the evaluation.

Attacks covered:
  1. Network → NGO private state  (proposal create/list/get/network-agent)
  2. Organization B → Organization A  (proposal IDs, targeting, legacy routes)
  3. Malicious body organization id  (seam must win, never the body)
  4. Legitimate proposal targeting  (public offer info may flow; private state may not)

Phase D is folded in: every assertion inspects the full serialized JSON of
the HTTP response, not internal Python objects.

NOTE: these tests prove server-side boundaries only. They do NOT assert any
authentication — any client can still select any org via the identity seam
(agent/org_context.py). What must hold is: cross-org and Network access to
private state is impossible through the API surface, regardless of which
org context the client selects.
"""

import os

# Repository mode is resolved by tests/conftest.py (_explicit_repo_mode):
# RELIEFOS_MEMORY=1 → InMemoryRepository; DATABASE_URL → PostgresRepository;
# neither → InMemory default. This file no longer forces memory mode, so the
# privacy suite can be verified against real PostgreSQL (Item 5B, Phase H).

import json
import shutil

import pytest

from agent.data.repository import get_repository, reset_repository


SECRET_A_ITEM = "SECRET_A_PRIVATE_ITEM_XYZ"
SECRET_A_TEAM = "SECRET_A_PRIVATE_TEAM_XYZ"
SECRET_A_MISSION = "SECRET_A_PRIVATE_MISSION_XYZ"

SECRET_B_ITEM = "SECRET_B_PRIVATE_ITEM_QRS"
SECRET_B_TEAM = "SECRET_B_PRIVATE_TEAM_QRS"
SECRET_B_MISSION = "SECRET_B_PRIVATE_MISSION_QRS"

ORG_A = "org_priv_a"
ORG_B = "org_priv_b"

ALL_SECRETS = [SECRET_A_ITEM, SECRET_A_TEAM, SECRET_A_MISSION,
               SECRET_B_ITEM, SECRET_B_TEAM, SECRET_B_MISSION]

# Keys that exist only in the RAW stored evaluation and must never appear
# in any HTTP response (network OR org-facing):
PRIVATE_EVAL_KEYS = ["private_factors", "org_evaluation", "team_assessment",
                     "mission_assessment"]


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_repo():
    reset_repository()
    get_repository()
    yield
    reset_repository()


@pytest.fixture(autouse=True)
def _purge_privacy_orgs():
    """The private workspace is FILE-backed and persists across runs.
    Purge this test's dedicated org dirs before AND after each test so the
    count-discriminator (A=3 vs B=2 resources) and secret markers are
    deterministic. Proposals live in the repository (PostgreSQL or InMemory,
    selected explicitly by conftest); no JSON file is involved.
    """
    import os
    orgs_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "orgs",
    )

    def _purge_file_state():
        for org in (ORG_A, ORG_B):
            shutil.rmtree(os.path.join(orgs_dir, org), ignore_errors=True)

    def _purge_db_rows():
        """In PostgreSQL mode, also purge this file's dedicated DB rows so
        re-runs are deterministic (orgs, their private resources/teams/
        missions, offers, needs, and proposals). Fixed test ids only — dev
        data is untouched.
        """
        if not os.environ.get("DATABASE_URL", "").strip() or os.environ.get(
            "RELIEFOS_MEMORY", ""
        ).strip() in ("1", "true", "yes"):
            return
        from agent.data.repository import get_repository
        from agent.data.schema import (
            coordination_proposals, organizations, needs, resource_offers,
            operations,
        )
        repo = get_repository()
        assert type(repo).__name__ == "PostgresRepository"
        # NOTE: private inventory/teams/missions are FILE-backed
        # (data/orgs/<org>/...), NOT DB tables — only the shared-network
        # entities live in PostgreSQL. The file purge above covers them.
        with repo._engine.begin() as conn:
            conn.execute(coordination_proposals.delete().where(
                coordination_proposals.c.organization_id.in_([ORG_A, ORG_B])
            ))
            conn.execute(operations.delete().where(
                operations.c.lead_organization_id.in_([ORG_A, ORG_B])
            ))
            conn.execute(resource_offers.delete().where(
                resource_offers.c.organization_id.in_([ORG_A, ORG_B])
            ))
            conn.execute(needs.delete().where(needs.c.id.like("need_priv_%")))
            conn.execute(organizations.delete().where(
                organizations.c.id.in_([ORG_A, ORG_B])
            ))

    _purge_file_state()
    _purge_db_rows()
    yield
    _purge_file_state()
    _purge_db_rows()


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


def _seed_private_state(client, org_id, item, team, mission, extra):
    """Seed private state. `item` rides as a private-only location string on
    a matching-type resource; `extra` is a private resource type that can
    never match a public need."""
    _select_org(client, org_id)
    r1 = client.post(
        "/api/my-org/resources",
        json={"resource_type": "rescue_boat", "quantity": 13, "unit": "units",
              "location": item},
    )
    assert r1.status_code == 201, r1.get_json()
    r2 = client.post(
        "/api/my-org/resources",
        json={"resource_type": item, "quantity": 5, "unit": "units"},
    )
    assert r2.status_code == 201, r2.get_json()
    if extra:
        r3 = client.post(
            "/api/my-org/resources",
            json={"resource_type": extra, "quantity": 7, "unit": "units"},
        )
        assert r3.status_code == 201, r3.get_json()
    t = client.post("/api/my-org/teams", json={"name": team})
    assert t.status_code == 201, t.get_json()
    m = client.post("/api/my-org/missions", json={"name": mission})
    assert m.status_code == 201, m.get_json()


def _publish_public_offer(client, org_id, resource_type, quantity):
    _select_org(client, org_id)
    resp = client.post(
        "/api/my-org/publish-offer",
        json={"resource_type": resource_type, "quantity": quantity, "unit": "units"},
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["offer"]


def _assert_no_secrets(payload, *forbidden_keys):
    """Phase D: inspect the full serialized JSON for private markers and
    private-only keys."""
    # default=str mirrors Flask's jsonify behavior for datetime/decimal
    # values that legitimately appear in DB-backed evidence records.
    blob = json.dumps(payload, default=str)
    for secret in ALL_SECRETS:
        assert secret not in blob, f"LEAK: {secret} in response: {blob[:500]}"
    for key in list(PRIVATE_EVAL_KEYS) + list(forbidden_keys):
        assert f'"{key}"' not in blob, f"private key '{key}' exposed: {blob[:500]}"


@pytest.fixture
def seeded(client):
    """Two real orgs with unmistakable private state + public offers.

    A: 3 private resources (rescue_boat×13 with secret location, secret-type
       ×5, water×7), 1 secret team, 1 secret mission, published offer
       rescue_boat×4.
    B: 2 private resources (rescue_boat×9 with secret location, secret-type
       ×3), 1 secret team, 1 secret mission, published offer rescue_boat×2.
    """
    _create_org(client, ORG_A, "Privacy Org A")
    _create_org(client, ORG_B, "Privacy Org B")

    _seed_private_state(client, ORG_A, SECRET_A_ITEM, SECRET_A_TEAM,
                        SECRET_A_MISSION, extra="water")
    _seed_private_state(client, ORG_B, SECRET_B_ITEM, SECRET_B_TEAM,
                        SECRET_B_MISSION, extra=None)

    offer_a = _publish_public_offer(client, ORG_A, "rescue_boat", 4)
    offer_b = _publish_public_offer(client, ORG_B, "rescue_boat", 2)

    need_resp = client.post(
        "/api/needs",
        json={
            "need_type": "rescue_boat",
            "title": "Boats needed at flood camp",
            "description": "Privacy boundary test need",
            "district_id": "jorhat",
            "lat": 26.75,
            "lon": 94.22,
            "urgency": "critical",
            "requested_resources": [{"resource_type": "rescue_boat", "quantity": 3, "unit": "units"}],
            "reporter_id": "privacy-audit",
        },
    )
    assert need_resp.status_code == 201, need_resp.get_json()
    need = need_resp.get_json()["need"]

    return {"offer_a": offer_a, "offer_b": offer_b, "need": need}


def _propose_for(client, seeded, org_id, org_name):
    resp = client.post(
        "/api/network/coordination/propose",
        json={"need": seeded["need"], "organization_id": org_id, "organization_name": org_name},
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["proposal"]["id"]


def _send_to_org(client, prop_id):
    resp = client.post(f"/api/network/coordination/proposals/{prop_id}/send-to-org")
    assert resp.status_code == 200, resp.get_json()
    _assert_no_secrets(resp.get_json())


# ---------------------------------------------------------------------------
# Attack 1 — Network → NGO private state
# ---------------------------------------------------------------------------

class TestAttack1NetworkToPrivate:
    def test_propose_response_has_no_private_state(self, client, seeded):
        resp = client.post(
            "/api/network/coordination/propose",
            json={"need": seeded["need"], "organization_id": ORG_A, "organization_name": "Privacy Org A"},
        )
        assert resp.status_code == 201, resp.get_json()
        _assert_no_secrets(resp.get_json())

    def test_proposal_list_and_detail_are_public_only(self, client, seeded):
        _propose_for(client, seeded, ORG_A, "Privacy Org A")

        listed = client.get("/api/network/coordination/proposals")
        assert listed.status_code == 200
        _assert_no_secrets(listed.get_json())

        prop_id = listed.get_json()["proposals"][0]["id"]
        detail = client.get(f"/api/network/coordination/proposals/{prop_id}")
        assert detail.status_code == 200
        _assert_no_secrets(detail.get_json())

    def test_network_agent_analysis_has_no_private_state(self, client, seeded):
        """Network Main Agent + workers must not pull org_workspace private state."""
        from agent.agents.network_main_agent import run_network_analysis
        result = run_network_analysis()
        _assert_no_secrets(result)

        # Structurally: no network-side module may import the private workspace
        import agent.agents.network_main_agent as nma
        import agent.agents.network_workers.coordination as cw
        import agent.agents.network_workers.logistics as lw
        for mod in (nma, cw, lw):
            with open(mod.__file__) as f:
                code = f.read()
            assert "org_workspace" not in code, f"{mod.__file__} imports private org workspace"

    def test_candidates_use_only_public_offer_data(self, client, seeded):
        from agent.coordination.candidate_selection import select_candidates
        candidates = select_candidates(seeded["need"])
        blob = json.dumps(candidates)
        for secret in ALL_SECRETS:
            assert secret not in blob
        # Legitimately public: A's published offer capability
        cand_a = [c for c in candidates if c["organization_id"] == ORG_A]
        assert cand_a, "A's published offer should make it a candidate"
        assert cand_a[0]["offer_type"] == "rescue_boat"
        assert cand_a[0]["total_public_quantity"] == 4  # published, not the private 13


# ---------------------------------------------------------------------------
# Attack 2 — Organization B → Organization A
# ---------------------------------------------------------------------------

class TestAttack2OrgBToOrgA:
    def _a_evaluates_own_proposal(self, client, seeded):
        """A evaluates a proposal targeting A (the legitimate org-side flow)."""
        prop_id = _propose_for(client, seeded, ORG_A, "Privacy Org A")
        _send_to_org(client, prop_id)

        _select_org(client, ORG_A)
        eval_resp = client.post(
            "/api/my-org/agent/evaluate-coordination",
            json={"proposal_id": prop_id},
        )
        assert eval_resp.status_code == 200, eval_resp.get_json()
        # Org-facing response is the public projection only
        _assert_no_secrets(eval_resp.get_json())

        # The RAW stored evaluation must have read A's private store:
        # A holds 3 private resources (B holds 2) — the count proves which
        # store was read. Secret strings never enter the evaluation by design
        # (factors are counts), so the count is the discriminator.
        from agent.coordination.proposal import get_proposal
        raw = get_proposal(prop_id)
        assert raw["org_evaluation"] is not None
        assert raw["org_evaluation"]["org_id"] == ORG_A
        assert raw["org_evaluation"]["resource_assessment"]["total_resources"] == 3
        assert raw["org_evaluation"]["resource_assessment"]["matching_available"] == 1
        return prop_id

    def test_detail_after_evaluation_still_public_only(self, client, seeded):
        prop_id = self._a_evaluates_own_proposal(client, seeded)
        detail = client.get(f"/api/network/coordination/proposals/{prop_id}")
        _assert_no_secrets(detail.get_json())
        listed = client.get("/api/network/coordination/proposals")
        _assert_no_secrets(listed.get_json())

    def test_send_to_org_returns_public_view_only(self, client, seeded):
        """send-to-org must never echo raw org_evaluation/private_factors."""
        prop_id = self._a_evaluates_own_proposal(client, seeded)
        resp = client.post(f"/api/network/coordination/proposals/{prop_id}/send-to-org")
        assert resp.status_code == 200
        _assert_no_secrets(resp.get_json())

    def test_decline_returns_public_view_only(self, client, seeded):
        prop_id = self._a_evaluates_own_proposal(client, seeded)
        resp = client.post(f"/api/network/coordination/proposals/{prop_id}/decline")
        assert resp.status_code == 200
        _assert_no_secrets(resp.get_json())

    def test_b_cannot_evaluate_proposal_targeting_a(self, client, seeded):
        """Only the TARGETED org may evaluate — B must not touch A's proposal."""
        prop_id = _propose_for(client, seeded, ORG_A, "Privacy Org A")
        _send_to_org(client, prop_id)

        _select_org(client, ORG_B)
        resp = client.post(
            "/api/my-org/agent/evaluate-coordination",
            json={"proposal_id": prop_id, "org_id": ORG_A, "organization_id": ORG_A},
        )
        assert resp.status_code == 404, f"B evaluated A's proposal: {resp.status_code}"

        # A's proposal must be untouched by B's attempt
        from agent.coordination.proposal import get_proposal
        raw = get_proposal(prop_id)
        assert raw["org_evaluation"] is None
        assert raw["private_factors"] is None

    def test_b_cannot_approve_publication_of_a_proposal(self, client, seeded):
        """B must not trigger publication using A's stored evaluation."""
        prop_id = self._a_evaluates_own_proposal(client, seeded)

        _select_org(client, ORG_B)
        before = client.get(f"/api/offers?organization_id={ORG_B}").get_json()["offers"]
        before_ids = {o["id"] for o in before}  # B's own published offer from the fixture

        resp = client.post(
            "/api/my-org/agent/approve-publication",
            json={"proposal_id": prop_id, "org_id": ORG_A},
        )
        assert resp.status_code == 404, f"B approved A's proposal: {resp.status_code}"

        # No NEW offer may have been created for B from A's evaluation
        offers = client.get(f"/api/offers?organization_id={ORG_B}").get_json()["offers"]
        assert {o["id"] for o in offers} == before_ids

    def test_legacy_arbitrary_org_routes_still_dead(self, client, seeded):
        for path in (
            f"/api/orgs/{ORG_A}/summary",
            f"/api/orgs/{ORG_A}/resources",
            f"/api/orgs/{ORG_A}/teams",
            f"/api/orgs/{ORG_A}/missions",
            f"/api/orgs/{ORG_A}/publish-offer",
            f"/api/orgs/{ORG_A}/agent/evaluate-coordination",
        ):
            resp = client.get(path)
            assert resp.status_code in (404, 405), f"{path} reachable: {resp.status_code}"

    def test_proposal_ids_cannot_cross_to_private_reads(self, client, seeded):
        """B enumerating A's proposal id gets only public fields."""
        prop_id = self._a_evaluates_own_proposal(client, seeded)
        _select_org(client, ORG_B)
        detail = client.get(f"/api/network/coordination/proposals/{prop_id}")
        assert detail.status_code == 200
        _assert_no_secrets(detail.get_json())


# ---------------------------------------------------------------------------
# Attack 3 — Malicious body organization id (seam must win)
# ---------------------------------------------------------------------------

class TestAttack3MaliciousBodyOrgId:
    def test_evaluate_uses_session_org_not_body_org(self, client, seeded):
        """B's session evaluating B's proposal with body claiming org A stays B."""
        prop_id = _propose_for(client, seeded, ORG_B, "Privacy Org B")
        _send_to_org(client, prop_id)

        _select_org(client, ORG_B)
        resp = client.post(
            "/api/my-org/agent/evaluate-coordination",
            json={"proposal_id": prop_id, "org_id": ORG_A, "organization_id": ORG_A},
        )
        assert resp.status_code == 200, resp.get_json()
        _assert_no_secrets(resp.get_json())

        # The recorded evaluation must belong to B (session org) and read B's
        # private store (2 resources), never A's (3 resources).
        from agent.coordination.proposal import get_proposal
        raw = get_proposal(prop_id)
        assert raw["org_evaluation"]["org_id"] == ORG_B
        assert raw["org_evaluation"]["resource_assessment"]["total_resources"] == 2

    def test_evaluate_response_never_leaks_other_org_private_state(self, client, seeded):
        """B evaluating its own proposal must not see A's private state anywhere."""
        prop_id = _propose_for(client, seeded, ORG_B, "Privacy Org B")
        _send_to_org(client, prop_id)

        _select_org(client, ORG_B)
        resp = client.post("/api/my-org/agent/evaluate-coordination", json={"proposal_id": prop_id})
        _assert_no_secrets(resp.get_json())
        body = resp.get_json()["evaluation"]
        assert body["public_summary"]  # B's own public summary present


# ---------------------------------------------------------------------------
# Attack 4 — Legitimate proposal targeting
# ---------------------------------------------------------------------------

class TestAttack4ProposalTargeting:
    def test_targeting_a_exposes_only_public_offer_capability(self, client, seeded):
        """B targeting A: A's public offer info flows; A's private state must not."""
        resp = client.post(
            "/api/network/coordination/propose",
            json={"need": seeded["need"], "organization_id": ORG_A, "organization_name": "Privacy Org A"},
        )
        assert resp.status_code == 201
        body = resp.get_json()

        proposal = body["proposal"]
        assert proposal["organization_id"] == ORG_A  # targeting is public metadata
        _assert_no_secrets(body)

        # Legitimately public: candidates carry PUBLISHED offer capability (4),
        # never the private inventory (13 + secret items).
        candidates = body["candidates"]
        cand_a = [c for c in candidates if c["organization_id"] == ORG_A]
        assert cand_a, "A must appear as candidate via its published offer"
        assert cand_a[0]["offer_quantity"] == 4
        assert cand_a[0]["total_public_quantity"] == 4

    def test_a_evaluating_own_proposal_keeps_secrets_server_side(self, client, seeded):
        """The NGO side MAY read its own private state — only public parts return."""
        prop_id = _propose_for(client, seeded, ORG_A, "Privacy Org A")
        _send_to_org(client, prop_id)

        _select_org(client, ORG_A)
        resp = client.post("/api/my-org/agent/evaluate-coordination", json={"proposal_id": prop_id})
        assert resp.status_code == 200
        _assert_no_secrets(resp.get_json())

        # Public projection may state capability, never raw private detail
        public_summary = resp.get_json()["evaluation"]["public_summary"]
        assert SECRET_A_ITEM not in public_summary

    def test_published_still_visible_on_network_after_full_lifecycle(self, client, seeded):
        """Legitimate cross-org flow: target evaluated + approved → public offer appears."""
        prop_id = _propose_for(client, seeded, ORG_A, "Privacy Org A")
        _send_to_org(client, prop_id)

        _select_org(client, ORG_A)
        eval_resp = client.post("/api/my-org/agent/evaluate-coordination", json={"proposal_id": prop_id})
        assert eval_resp.status_code == 200
        _assert_no_secrets(eval_resp.get_json())

        approve_resp = client.post("/api/my-org/agent/approve-publication", json={"proposal_id": prop_id})
        assert approve_resp.status_code == 200, approve_resp.get_json()
        _assert_no_secrets(approve_resp.get_json())

        # The published offer belongs to A and is visible on the shared network
        offers = client.get(f"/api/offers?organization_id={ORG_A}").get_json()["offers"]
        assert offers, "Approved publication must create a visible public offer"
        for offer in offers:
            assert offer["organization_id"] == ORG_A
            _assert_no_secrets(offer)
