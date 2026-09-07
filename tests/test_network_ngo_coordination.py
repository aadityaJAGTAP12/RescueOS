"""
Tests for Network ↔ NGO Coordination — Phase 7H

Privacy and security tests proving:
1. Network cannot read NGO private state
2. Private factors never appear in public output
3. Human approval is required before publication
4. Published offers contain only approved fields
5. Existing collaboration lifecycle still works
"""

import pytest
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# DB-mode fixture: these tests use fixed org ids (org_test/org_1) that must
# exist in PostgreSQL when DATABASE_URL is set (resource_offers has a real
# FK to organizations). Memory mode has no FK enforcement, so this is a
# no-op there.
# ---------------------------------------------------------------------------

_DB_ORGS = ("org_test", "org_1")
_CREATED_PROPOSAL_IDS: set = set()


@pytest.fixture(autouse=True)
def _ensure_db_orgs():
    if os.environ.get("RELIEFOS_MEMORY", "").strip() in ("1", "true", "yes") or not \
            os.environ.get("DATABASE_URL", "").strip():
        yield
        return
    from agent.data.repository import get_repository
    from agent.data.models import Organization
    from sqlalchemy import select
    from agent.data.schema import coordination_proposals
    repo = get_repository()
    assert type(repo).__name__ == "PostgresRepository", (
        "DATABASE_URL set but repository is not PostgresRepository"
    )
    for org_id, name in (("org_test", "Test Org"), ("org_1", "Org 1")):
        if repo.get_organization(org_id) is None:
            repo.create_organization(Organization(id=org_id, name=name))
    # Snapshot the pre-existing proposal ids for this module's orgs BEFORE
    # the test runs, so teardown deletes exactly the rows the test added.
    with repo._engine.begin() as conn:
        _CREATED_PROPOSAL_IDS.clear()
        _CREATED_PROPOSAL_IDS.update(
            row.id for row in conn.execute(
                select(coordination_proposals.c.id).where(
                    coordination_proposals.c.organization_id.in_(_DB_ORGS)
                )
            )
        )
    yield
    # Proposals created by these tests are cleaned up to keep the DB tidy.
    # CRITICAL (Item 5B): cleanup deletes ONLY ids that appeared during the
    # test (current minus the pre-test snapshot) — NEVER by organization_id.
    # The org_1 batch includes the legitimate migrated legacy proposals; an
    # organization-scoped delete here wiped the whole migrated batch during
    # the Item 5B DB regression run. The orgs are left in place (harmless,
    # reused across runs).
    with repo._engine.begin() as conn:
        current_ids = {
            row.id for row in conn.execute(
                select(coordination_proposals.c.id).where(
                    coordination_proposals.c.organization_id.in_(_DB_ORGS)
                )
            )
        }
        new_ids = current_ids - _CREATED_PROPOSAL_IDS
        if new_ids:
            conn.execute(coordination_proposals.delete().where(
                coordination_proposals.c.id.in_(list(new_ids))
            ))
        _CREATED_PROPOSAL_IDS.clear()


# ---------------------------------------------------------------------------
# Test: Coordination Proposal lifecycle
# ---------------------------------------------------------------------------

class TestProposalLifecycle:
    def test_create_proposal(self):
        from agent.coordination.proposal import create_proposal, get_proposal
        proposal = create_proposal(
            need_id="need_test",
            organization_id="org_test",
            organization_name="Test Org",
            proposal_type="boat",
            summary="Test proposal",
        )
        assert proposal["status"] == "PROPOSED"
        assert proposal["need_id"] == "need_test"
        assert proposal["organization_id"] == "org_test"

        # Retrieve
        fetched = get_proposal(proposal["id"])
        assert fetched is not None
        assert fetched["id"] == proposal["id"]

    def test_send_to_org(self):
        from agent.coordination.proposal import create_proposal, send_to_org, get_proposal
        proposal = create_proposal(
            need_id="need_1",
            organization_id="org_1",
            organization_name="Org 1",
            proposal_type="boat",
            summary="Test",
        )
        updated = send_to_org(proposal["id"])
        assert updated["status"] == "PENDING_ORG_REVIEW"

    def test_decline_proposal(self):
        from agent.coordination.proposal import create_proposal, decline_proposal, get_proposal
        proposal = create_proposal(
            need_id="need_1",
            organization_id="org_1",
            organization_name="Org 1",
            proposal_type="boat",
            summary="Test",
        )
        declined = decline_proposal(proposal["id"])
        assert declined["status"] == "DECLINED"


# ---------------------------------------------------------------------------
# Test: Private state never leaks to network
# ---------------------------------------------------------------------------

class TestPrivacyBoundary:
    def test_public_view_excludes_private(self):
        """Public view must never contain private_factors or raw org_evaluation."""
        from agent.coordination.proposal import create_proposal, record_org_evaluation, get_proposal, get_public_view

        proposal = create_proposal(
            need_id="need_1",
            organization_id="org_1",
            organization_name="Org 1",
            proposal_type="boat",
            summary="Test",
        )

        # Record private evaluation
        record_org_evaluation(
            proposal["id"],
            evaluation={"decision": "SUITABLE", "private_data": "SECRET"},
            private_factors=["Factor 1: secret inventory count", "Factor 2: private team name"],
        )

        # Get public view
        public = get_public_view(get_proposal(proposal["id"]))

        # Verify private data is NOT in public view
        public_str = json.dumps(public)
        assert "SECRET" not in public_str
        assert "Factor 1" not in public_str
        assert "Factor 2" not in public_str
        assert "private_data" not in public_str
        assert "private_factors" not in public_str

    def test_org_view_excludes_private_factors(self):
        """Org view should not expose raw private_factors."""
        from agent.coordination.proposal import create_proposal, record_org_evaluation, get_proposal, get_org_view

        proposal = create_proposal(
            need_id="need_1",
            organization_id="org_1",
            organization_name="Org 1",
            proposal_type="boat",
            summary="Test",
        )

        record_org_evaluation(
            proposal["id"],
            evaluation={"decision": "SUITABLE"},
            private_factors=["Secret factor"],
        )

        org_view = get_org_view(get_proposal(proposal["id"]))
        org_str = json.dumps(org_view)
        assert "Secret factor" not in org_str

    def test_private_factors_not_in_api_response(self):
        """API response should not contain private_factors."""
        from agent.coordination.proposal import create_proposal, record_org_evaluation, get_proposal, get_public_view

        proposal = create_proposal(
            need_id="need_1",
            organization_id="org_1",
            organization_name="Org 1",
            proposal_type="boat",
            summary="Test",
        )

        record_org_evaluation(
            proposal["id"],
            evaluation={"decision": "SUITABLE"},
            private_factors=["Private inventory detail"],
        )

        # Simulate API response (public view)
        public = get_public_view(get_proposal(proposal["id"]))
        assert "private_factors" not in public
        assert "Private inventory detail" not in json.dumps(public)


# ---------------------------------------------------------------------------
# Test: Human approval required
# ---------------------------------------------------------------------------

class TestHumanApproval:
    def test_cannot_publish_without_approval(self):
        """Publication requires explicit human approval."""
        from agent.coordination.proposal import create_proposal, record_org_evaluation, get_proposal

        proposal = create_proposal(
            need_id="need_1",
            organization_id="org_1",
            organization_name="Org 1",
            proposal_type="boat",
            summary="Test",
        )

        record_org_evaluation(
            proposal["id"],
            evaluation={"decision": "SUITABLE"},
            private_factors=[],
        )

        # Proposal should still be ORG_RECOMMENDED, not PUBLISHED
        fetched = get_proposal(proposal["id"])
        assert fetched["status"] == "ORG_RECOMMENDED"
        assert fetched["approved_at"] is None

    def test_approval_sets_status(self):
        """Approval transitions to PUBLISHED."""
        from agent.coordination.proposal import create_proposal, approve_publication, get_proposal

        proposal = create_proposal(
            need_id="need_1",
            organization_id="org_1",
            organization_name="Org 1",
            proposal_type="boat",
            summary="Test",
        )

        approved = approve_publication(proposal["id"], approved_by="test_user")
        assert approved["status"] == "PUBLISHED"
        assert approved["approved_by"] == "test_user"
        assert approved["approved_at"] is not None


# ---------------------------------------------------------------------------
# Test: Publication creates valid public offer
# ---------------------------------------------------------------------------

class TestPublication:
    def test_publication_creates_offer(self):
        """Approved publication creates a public Resource Offer."""
        from agent.coordination.proposal import create_proposal, record_org_evaluation, approve_publication
        from agent.coordination.publication import create_public_offer_from_proposal
        from agent.data.repository import get_repository

        proposal = create_proposal(
            need_id="need_1",
            organization_id="org_1",
            organization_name="Org 1",
            proposal_type="boat",
            summary="Test",
        )

        evaluation = {
            "decision": "SUITABLE",
            "resource_assessment": {"matching_available": 2},
            "private_factors": ["SECRET: 5 boats in inventory"],
            "constraints": ["Launch point needs verification"],
        }

        record_org_evaluation(proposal["id"], evaluation, evaluation["private_factors"])
        approve_publication(proposal["id"])

        # Create offer
        repo = get_repository()
        result = create_public_offer_from_proposal(proposal, evaluation, "org_1", repo)

        assert result["offer"] is not None
        assert result["offer"]["organization_id"] == "org_1"
        assert result["offer"]["resource_type"] == "boat"
        assert result["offer"]["status"] == "OFFERED"

        # Verify private data not in offer
        offer_str = json.dumps(result["offer"])
        assert "SECRET" not in offer_str
        assert "5 boats in inventory" not in offer_str

    def test_publication_respects_constraints(self):
        """Published offer includes approved constraints."""
        from agent.coordination.proposal import create_proposal, record_org_evaluation, approve_publication
        from agent.coordination.publication import create_public_offer_from_proposal
        from agent.data.repository import get_repository

        proposal = create_proposal(
            need_id="need_1",
            organization_id="org_1",
            organization_name="Org 1",
            proposal_type="boat",
            summary="Test",
            constraints=["Requires safe launch point"],
        )

        evaluation = {
            "decision": "SUITABLE",
            "resource_assessment": {"matching_available": 1},
            "private_factors": [],
            "constraints": ["Requires safe launch point"],
        }

        record_org_evaluation(proposal["id"], evaluation, [])
        approve_publication(proposal["id"])

        repo = get_repository()
        result = create_public_offer_from_proposal(proposal, evaluation, "org_1", repo)

        # Constraint should be in the offer notes
        assert "Requires safe launch point" in result["offer"]["notes"]


# ---------------------------------------------------------------------------
# Test: Candidate selection uses public info only
# ---------------------------------------------------------------------------

class TestCandidateSelection:
    def test_uses_public_offers_only(self):
        """Candidate selection should only use published offers."""
        from agent.coordination.candidate_selection import select_candidates
        from agent.data.repository import get_repository

        repo = get_repository()
        candidates = select_candidates(
            {"id": "need_1", "need_type": "boat", "title": "Boats needed"},
            repo,
        )
        # Should not crash and should return a list
        assert isinstance(candidates, list)


# ---------------------------------------------------------------------------
# Test: NGO evaluation uses private state
# ---------------------------------------------------------------------------

class TestNGOEvaluation:
    def test_evaluation_uses_private_state(self):
        """NGO evaluation should consider private resources."""
        from agent.coordination.ngo_evaluation import evaluate_coordination

        proposal = {
            "id": "prop_1",
            "need_id": "need_1",
            "proposal_type": "boat",
        }

        # This will use the JSON file storage (empty in test)
        result = evaluate_coordination(proposal, "org_nonexistent")

        assert "decision" in result
        assert "private_factors" in result
        assert "public_summary" in result
        # Private factors should be present in the result (stored locally)
        assert isinstance(result["private_factors"], list)


# ---------------------------------------------------------------------------
# Test: Audit trail
# ---------------------------------------------------------------------------

class TestAuditTrail:
    def test_proposal_has_timestamps(self):
        """Proposals should have creation timestamps."""
        from agent.coordination.proposal import create_proposal

        proposal = create_proposal(
            need_id="need_1",
            organization_id="org_1",
            organization_name="Org 1",
            proposal_type="boat",
            summary="Test",
        )

        assert "created_at" in proposal
        assert "updated_at" in proposal
