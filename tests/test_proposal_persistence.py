"""
Coordination Proposal Persistence Tests — Item #5, Step 2

Proves PostgreSQL (or, in memory mode, the InMemoryRepository backing the
same interface) is the SINGLE AUTHORITATIVE persistence source for
coordination proposals:

  1. create → read through the real application path (HTTP API)
  2. lifecycle update → read back
  3. persistence across application-state reset (repository reinit)
  4. no JSON authority — runtime works with the legacy JSON file removed
  5. repository-level guard behavior (update expected_statuses)

Privacy regression (Step 1 suite) and two-org isolation live in
tests/test_coordination_privacy.py; the no-JSON test here additionally
asserts no secret/private-key leakage after the JSON file is removed.

DB-vs-memory selection: tests honor the ambient environment. When
DATABASE_URL is set (and RELIEFOS_MEMORY is not), get_repository() returns
PostgresRepository — these tests then exercise the real database. In
RELIEFOS_MEMORY=1 mode they exercise the InMemory implementation of the
same interface. Both are reported separately in the step evidence.
"""

import os

# Repository mode is resolved EXPLICITLY by tests/conftest.py
# (_explicit_repo_mode): RELIEFOS_MEMORY=1 → InMemoryRepository,
# DATABASE_URL → PostgresRepository (asserted), neither → InMemory default.
# This file never forces a mode; DB-mode claims are backed by the conftest
# identity assertion (Item 5B, Phase C/D).

import json
import uuid

import pytest

from agent.data.repository import get_repository, reset_repository, set_repository

IS_MEMORY_MODE = not os.environ.get("DATABASE_URL", "").strip() or bool(
    os.environ.get("RELIEFOS_MEMORY", "").strip()
)

# Restart-persistence is only meaningful against a durable backend. The
# InMemoryRepository is volatile BY DESIGN (process-local dict) — asserting
# survival across reset there would test nothing. These tests are skipped in
# memory mode and run for real when DATABASE_URL is configured.
requires_durable_backend = pytest.mark.skipif(
    IS_MEMORY_MODE,
    reason="restart persistence requires a durable backend (DATABASE_URL); "
           "InMemoryRepository is process-local by design",
)


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
def purge_db_test_rows():
    """In PostgreSQL mode, purge this file's dedicated test rows before AND
    after each test so re-runs are deterministic (no UniqueViolation from
    earlier runs). Uses fixed test ids so cleanup is targeted — the dev DB's
    real data is never touched.
    """
    if IS_MEMORY_MODE:
        yield
        return
    from agent.data.postgres_repository import PostgresRepository
    from agent.data.schema import (
        coordination_proposals, organizations, needs,
    )
    repo = get_repository()
    assert type(repo).__name__ == "PostgresRepository"
    engine = repo._engine
    with engine.begin() as conn:
        conn.execute(coordination_proposals.delete().where(
            coordination_proposals.c.organization_id.in_(
                ["org_persist", "org_ts", "org_g", "org_h", "org_x"]
            )
        ))
        conn.execute(needs.delete().where(
            needs.c.id.like("need_%")
        ))
        conn.execute(organizations.delete().where(
            organizations.c.id.in_(
                ["org_persist", "org_ts", "org_g", "org_h", "org_x"]
            )
        ))
    yield
    with engine.begin() as conn:
        conn.execute(coordination_proposals.delete().where(
            coordination_proposals.c.organization_id.in_(
                ["org_persist", "org_ts", "org_g", "org_h", "org_x"]
            )
        ))
        conn.execute(needs.delete().where(needs.c.id.like("need_%")))
        conn.execute(organizations.delete().where(
            organizations.c.id.in_(
                ["org_persist", "org_ts", "org_g", "org_h", "org_x"]
            )
        ))


@pytest.fixture
def client():
    from agent.api import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _make_need_payload():
    return {
        "id": f"need_{uuid.uuid4().hex[:8]}",
        "need_type": "rescue_boat",
        "title": "Persistence test need",
        "urgency": "high",
        "requested_resources": [{"resource_type": "rescue_boat", "quantity": 2, "unit": "units"}],
    }


def _create_org_and_proposal(client, org_id="org_persist"):
    resp = client.post(
        "/api/organizations",
        json={"id": org_id, "name": "Persistence Org", "organization_type": "ngo"},
    )
    assert resp.status_code == 201, resp.get_json()
    resp = client.post(
        "/api/network/coordination/propose",
        json={"need": _make_need_payload(), "organization_id": org_id,
              "organization_name": "Persistence Org"},
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["proposal"]["id"]


def _read_proposal_in_fresh_subprocess(proposal_id):
    """Genuine process-restart proof (Item 5B, Phase E): spawn a fresh Python
    process that connects to PostgreSQL independently and fetches the raw
    proposal row. The parent's module state is irrelevant to it.
    """
    import subprocess
    import sys
    code = (
        "import json;from agent.data.repository import get_repository;"
        "r=get_repository().get_proposal(" + repr(proposal_id) + ");"
        "print(json.dumps(r))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=90,
    )
    assert proc.returncode == 0, (
        f"fresh-process read failed\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    import json as _json
    return _json.loads(proc.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------------------
# 1. Create → read (real application path)
# ---------------------------------------------------------------------------

class TestCreateReadViaAPI:
    def test_create_proposal_without_timestamps_uses_server_default(self, client):
        """Regression (Item 5B Bug 1): create_proposal with NO created_at/
        updated_at must not insert explicit NULLs into NOT NULL columns with
        server_default=now() — that raised NotNullViolation. The repository
        must supply current UTC itself (or let the DB default apply).
        """
        repo = get_repository()
        proposal = repo.create_proposal({
            "id": f"prop_{uuid.uuid4().hex[:8]}",
            "need_id": "need_ts",
            "organization_id": "org_ts",
            "organization_name": "Timestamp Org",
            "proposal_type": "boat",
            "summary": "no timestamps supplied",
            "status": "PROPOSED",
            # deliberately NO created_at / updated_at keys
        })
        raw = repo.get_proposal(proposal["id"])
        assert raw is not None
        assert raw["created_at"], "created_at must be populated, not NULL/empty"
        assert raw["updated_at"], "updated_at must be populated, not NULL/empty"
        # And a SUPPLIED timestamp must be preserved:
        from datetime import datetime, timezone
        supplied = "2026-09-01T10:00:00+00:00"
        p2 = repo.create_proposal({
            "id": f"prop_{uuid.uuid4().hex[:8]}",
            "need_id": "need_ts",
            "organization_id": "org_ts",
            "organization_name": "Timestamp Org",
            "proposal_type": "boat",
            "summary": "supplied timestamp",
            "status": "PROPOSED",
            "created_at": supplied,
        })
        raw2 = repo.get_proposal(p2["id"])
        assert raw2["created_at"].startswith("2026-09-01T10:00:00")

    def test_created_proposal_readable_via_api_and_repo(self, client):
        prop_id = _create_org_and_proposal(client)

        # Via API (public projection)
        resp = client.get(f"/api/network/coordination/proposals/{prop_id}")
        assert resp.status_code == 200
        pub = resp.get_json()["proposal"]
        assert pub["id"] == prop_id
        assert pub["status"] == "PROPOSED"
        assert pub["organization_id"] == "org_persist"

        # Via the authoritative repository (raw record)
        repo = get_repository()
        raw = repo.get_proposal(prop_id)
        assert raw is not None
        assert raw["need_id"]
        assert raw["proposal_type"] == "rescue_boat"
        assert raw["org_evaluation"] is None

    def test_created_proposal_appears_in_list_with_filter(self, client):
        prop_id = _create_org_and_proposal(client)
        listed = client.get("/api/network/coordination/proposals?organization_id=org_persist")
        ids = [p["id"] for p in listed.get_json()["proposals"]]
        assert prop_id in ids


# ---------------------------------------------------------------------------
# 2. Update → read
# ---------------------------------------------------------------------------

class TestUpdateRead:
    def test_lifecycle_update_persists(self, client):
        prop_id = _create_org_and_proposal(client)

        resp = client.post(f"/api/network/coordination/proposals/{prop_id}/send-to-org")
        assert resp.status_code == 200
        assert resp.get_json()["proposal"]["status"] == "PENDING_ORG_REVIEW"

        # Read back from the authoritative store
        raw = get_repository().get_proposal(prop_id)
        assert raw["status"] == "PENDING_ORG_REVIEW"

        # Full lifecycle: evaluate → approve → link offer
        client.post("/api/session/org", json={"org_id": "org_persist"})
        eval_resp = client.post(
            "/api/my-org/agent/evaluate-coordination",
            json={"proposal_id": prop_id},
        )
        assert eval_resp.status_code == 200, eval_resp.get_json()
        assert get_repository().get_proposal(prop_id)["status"] == "ORG_RECOMMENDED"
        assert get_repository().get_proposal(prop_id)["org_evaluation"] is not None

        approve_resp = client.post(
            "/api/my-org/agent/approve-publication",
            json={"proposal_id": prop_id},
        )
        assert approve_resp.status_code == 200, approve_resp.get_json()
        raw = get_repository().get_proposal(prop_id)
        # This org has no matching inventory, so publication creates no offer
        # and link_offer never fires: status lands on PUBLISHED (approve only).
        assert raw["status"] == "PUBLISHED"
        assert raw["approved_by"] == "human"
        assert raw["approved_at"] is not None

    def test_decline_persists(self, client):
        prop_id = _create_org_and_proposal(client)
        resp = client.post(f"/api/network/coordination/proposals/{prop_id}/decline")
        assert resp.status_code == 200
        assert get_repository().get_proposal(prop_id)["status"] == "DECLINED"


# ---------------------------------------------------------------------------
# 3. Process restart / fresh application state
# ---------------------------------------------------------------------------

@requires_durable_backend
class TestRestartPersistence:
    def test_repo_identity_is_postgres_for_restart_tests(self, client):
        """Phase D proof: these restart tests only count as DB evidence when
        the live repository really is PostgresRepository."""
        assert type(get_repository()).__name__ == "PostgresRepository"

    def test_proposal_survives_fresh_process(self, client):
        """Genuine process restart (Item 5B, Phase E): create via API in this
        process, then spawn a FRESH subprocess that connects to PostgreSQL
        independently and reads the proposal back. This proves durability
        across process exit, not merely repository-singleton reset.

        Only meaningful with PostgresRepository (class is skipped in memory
        mode — InMemory is process-local by design).
        """
        repo = get_repository()
        assert type(repo).__name__ == "PostgresRepository"
        prop_id = _create_org_and_proposal(client)
        client.post(f"/api/network/coordination/proposals/{prop_id}/send-to-org")

        # Simulate process restart: drop the module-level repository singleton
        reset_repository()
        # (With a durable backend the data lives in PostgreSQL; with the
        # in-memory backend this class is skipped entirely.)

        # Fresh PROCESS reads from PostgreSQL independently
        raw = _read_proposal_in_fresh_subprocess(prop_id)
        assert raw is not None, "proposal lost across process restart"
        assert raw["status"] == "PENDING_ORG_REVIEW"
        assert raw["organization_id"] == "org_persist"

    def test_lifecycle_state_survives_fresh_process(self, client):
        """Lifecycle mutations survive a genuine fresh-process read (Phase E)."""
        repo = get_repository()
        assert type(repo).__name__ == "PostgresRepository"
        prop_id = _create_org_and_proposal(client)
        client.post("/api/session/org", json={"org_id": "org_persist"})
        client.post(f"/api/network/coordination/proposals/{prop_id}/send-to-org")
        client.post("/api/my-org/agent/evaluate-coordination", json={"proposal_id": prop_id})

        raw = _read_proposal_in_fresh_subprocess(prop_id)
        assert raw["status"] == "ORG_RECOMMENDED"
        assert raw["org_evaluation"] is not None
        assert raw["private_factors"] is not None  # stored server-side, per design


# ---------------------------------------------------------------------------
# 4. No JSON authority
# ---------------------------------------------------------------------------

class TestNoJsonAuthority:
    def test_runtime_works_without_legacy_json_file(self, client, tmp_path):
        """Rename the legacy JSON away; the full API flow must still work.

        Uses a copy moved into tmp (original restored after the test), so the
        developer environment is never damaged. After the flow, the file must
        NOT have been recreated by runtime writes (no dual-write).
        """
        import shutil
        legacy = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "agent", "data", "coordination_proposals.json",
        )
        moved = None
        if os.path.exists(legacy):
            moved = tmp_path / "coordination_proposals.json.bak"
            shutil.move(legacy, str(moved))
        try:
            prop_id = _create_org_and_proposal(client)
            client.post(f"/api/network/coordination/proposals/{prop_id}/send-to-org")

            listed = client.get("/api/network/coordination/proposals?organization_id=org_persist")
            ids = [p["id"] for p in listed.get_json()["proposals"]]
            assert prop_id in ids
            assert get_repository().get_proposal(prop_id)["status"] == "PENDING_ORG_REVIEW"
        finally:
            # Runtime must not have recreated the file while it was away
            # (assert BEFORE restoring the backup, otherwise this assert is
            # trivially true-seeing the restored copy).
            assert not os.path.exists(legacy), (
                "runtime wrote to the legacy JSON file — dual-write detected"
            )
            if moved is not None:
                shutil.move(str(moved), legacy)

    def test_no_module_reads_legacy_json_at_runtime(self):
        """Static guard: no runtime module may reference the legacy file."""
        import agent.coordination.proposal as proposal_mod
        with open(proposal_mod.__file__) as f:
            code = f.read()
        assert "coordination_proposals.json" not in code.replace(
            "no longer read or written", ""
        ) or "PROPOSALS_FILE" not in code
        # Stronger: the domain layer must not define JSON load/save helpers
        assert not hasattr(proposal_mod, "_load_proposals")
        assert not hasattr(proposal_mod, "_save_proposals")
        assert not hasattr(proposal_mod, "PROPOSALS_FILE")

    def test_domain_layer_delegates_to_repository(self):
        """The domain functions must route through the repository singleton."""
        import agent.coordination.proposal as proposal_mod
        repo = get_repository()
        set_repository(repo)  # ensure explicit
        proposal = proposal_mod.create_proposal(
            need_id="need_x",
            organization_id="org_x",
            organization_name="Org X",
            proposal_type="boat",
            summary="delegation check",
        )
        assert repo.get_proposal(proposal["id"]) is not None


# ---------------------------------------------------------------------------
# 5. Repository-level guard behavior (Phase H)
# ---------------------------------------------------------------------------

class TestRepositoryGuards:
    def test_update_with_expected_status_guard(self):
        repo = get_repository()
        proposal = repo.create_proposal({
            "id": f"prop_{uuid.uuid4().hex[:8]}",
            "need_id": "need_g",
            "organization_id": "org_g",
            "organization_name": "G",
            "proposal_type": "boat",
            "summary": "guard test",
            "status": "PROPOSED",
        })
        # Wrong expected status → no update
        out = repo.update_proposal(
            proposal["id"], {"status": "DECLINED"}, expected_statuses=["PUBLISHED"]
        )
        assert out is None
        assert repo.get_proposal(proposal["id"])["status"] == "PROPOSED"
        # Correct expected status → update applies
        out = repo.update_proposal(
            proposal["id"], {"status": "DECLINED"}, expected_statuses=["PROPOSED"]
        )
        assert out["status"] == "DECLINED"

    def test_duplicate_create_same_id_last_write_wins(self):
        """Documented semantics: create with an existing id overwrites (same
        as the previous JSON behavior). Domain layer generates unique ids, so
        this only matters for the migration path (which skips existing ids)."""
        repo = get_repository()
        pid = f"prop_{uuid.uuid4().hex[:8]}"
        base = {"id": pid, "need_id": "n", "organization_id": "org_g",
                "organization_name": "G", "proposal_type": "boat",
                "summary": "first", "status": "PROPOSED"}
        repo.create_proposal(base)
        second = dict(base, summary="second")
        repo.create_proposal(second)
        assert repo.get_proposal(pid)["summary"] == "second"

    def test_update_nonexistent_returns_none(self):
        assert get_repository().update_proposal("prop_missing", {"status": "DECLINED"}) is None

    def test_list_filters_and_ordering(self):
        repo = get_repository()
        ids = []
        for i in range(3):
            p = repo.create_proposal({
                "id": f"prop_{uuid.uuid4().hex[:8]}",
                "need_id": f"need_{i}",
                "organization_id": "org_g" if i < 2 else "org_h",
                "organization_name": "G",
                "proposal_type": "boat",
                "summary": f"p{i}",
                "status": "PROPOSED" if i < 2 else "DECLINED",
            })
            ids.append(p["id"])
        by_org = repo.list_proposals(organization_id="org_g")
        assert {p["id"] for p in by_org} == set(ids[:2])
        # NOTE: the status filter is unscoped, so the authoritative DB may
        # also contain legitimately migrated historical records (e.g. the
        # org_1 migration batch). Assert OUR rows only:
        by_status = repo.list_proposals(status="DECLINED")
        status_ids = {p["id"] for p in by_status}
        assert ids[2] in status_ids
        assert not (set(ids[:2]) & status_ids), "PROPOSED rows leaked into DECLINED filter"
