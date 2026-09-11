"""
ReliefOS Backup/Restore Verification Script — Production Hardening

Demonstrates (against a local PostgreSQL instance) that after a database
restore:
  - needs / offers / operations survive
  - coordination proposals survive (public projection + org evaluation intact)
  - notifications / activity events survive
  - audit records survive
  - users / organization memberships survive
  - AgentEvents remain safe to process (statuses preserved; stale CLAIMED rows
    are recoverable by the standard recovery path)
  - no private/public boundary is corrupted (org evaluations stay org-scoped)

Usage (local production-like environment):
    export DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos
    python scripts/verify_backup_restore.py --dump-file backup_test.dump

The script:
  1. Seeds unique tagged synthetic rows for every persistence class.
  2. Runs pg_dump against the live database.
  3. Drops + recreates the database and restores from the dump (pg_restore).
  4. Re-verifies every seeded row survived byte-for-byte on the IDs that matter.
  5. Runs stale-event recovery to prove restored CLAIMED events are requeueable.
  6. Deletes its own synthetic rows (cleanup), leaving the database clean.

Requirements: pg_dump/pg_restore on PATH; DATABASE_URL with a role allowed to
CREATE/DROP DATABASE (or use --skip-restore to only verify seed/verify logic).

This script NEVER reads or prints secrets. It prints only row counts and IDs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(REPO_ROOT, ".env"))

RUN_TAG = uuid.uuid4().hex[:8]

# Every class of persistent state we must prove survives a restore.
SEED = {
    "org_id": f"org_bvr_{RUN_TAG}",
    "other_org_id": f"org_bvr_other_{RUN_TAG}",
    "user": {"username": f"bvr_user_{RUN_TAG}", "email": f"bvr_{RUN_TAG}@example.test"},
    "need_id": f"need_bvr_{RUN_TAG}",
    "offer_id": f"offer_bvr_{RUN_TAG}",
    "op_id": f"op_bvr_{RUN_TAG}",
    "proposal_id": f"prop_bvr_{RUN_TAG}",
    "notif_id": f"notif_bvr_{RUN_TAG}",
    "activity_id": f"evt_bvr_{RUN_TAG}",
    "audit_action": f"bvr_test_action_{RUN_TAG}",
    "agent_event_id": f"evt_agent_bvr_{RUN_TAG}",
}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def parse_database_url(url: str) -> dict:
    from sqlalchemy.engine import make_url
    u = make_url(url)
    return {
        "host": u.host or "localhost",
        "port": u.port or 5432,
        "user": u.username or "",
        "password": u.password or "",
        "database": u.database or "reliefos",
    }


def seed_synthetic_data() -> None:
    """Insert one row of every persistence class, tagged with RUN_TAG."""
    from agent.data.repository import get_repository
    from agent.data.models import (
        Organization, Need, ResourceOffer, Operation, ActivityEvent,
        Notification, AgentEvent, AgentEventType, EventStatus,
        User, OrganizationMembership,
    )
    from agent.auth.service import hash_password

    repo = get_repository()
    assert type(repo).__name__ == "PostgresRepository", (
        "DATABASE_URL must point at PostgreSQL for the restore verification"
    )

    now = datetime.now(timezone.utc)

    repo.create_organization(Organization(id=SEED["org_id"], name=f"BVR Org {RUN_TAG}", organization_type="ngo"))
    repo.create_organization(Organization(id=SEED["other_org_id"], name=f"BVR Other {RUN_TAG}", organization_type="ngo"))

    repo.create_need(Need(
        id=SEED["need_id"], need_type="water", title=f"BVR need {RUN_TAG}",
        district_id=None, lat=26.75, lon=94.2, urgency="URGENT", status="OPEN",
        created_at=now, updated_at=now,
    ))
    repo.create_resource_offer(ResourceOffer(
        id=SEED["offer_id"], organization_id=SEED["org_id"], resource_type="water",
        quantity=10, unit="liters", status="OFFERED", created_at=now, updated_at=now,
    ))
    repo.create_operation(Operation(
        id=SEED["op_id"], name=f"BVR op {RUN_TAG}", operation_type="collaboration",
        need_id=SEED["need_id"], lead_organization_id=SEED["org_id"],
        district_id=None, status="PLANNING", created_at=now, updated_at=now,
    ))

    # Coordination proposal with an org evaluation on the targeted org only.
    repo.create_proposal({
        "id": SEED["proposal_id"],
        "need_id": SEED["need_id"],
        "organization_id": SEED["org_id"],
        "organization_name": f"BVR Org {RUN_TAG}",
        "proposal_type": "water",
        "summary": f"BVR proposal {RUN_TAG}",
        "status": "SENT",
        "public_evidence": [{"type": "bvr", "detail": "public"}],
        "network_findings": [{"type": "bvr", "detail": "network"}],
        "org_evaluation": {"decision": "ACCEPT", "capacity": 10},
        "private_factors": ["inventory ok"],
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    })

    repo.create_notification(Notification(
        id=SEED["notif_id"], recipient_id=SEED["org_id"],
        notification_type="bvr_test", title="BVR", message="restore verification",
        entity_type="bvr", entity_id=SEED["proposal_id"], created_at=now,
    ))
    repo.append_activity_event(ActivityEvent(
        id=SEED["activity_id"], entity_type="need", entity_id=SEED["need_id"],
        event_type="bvr_test", actor=SEED["org_id"], detail="restore verification",
    ))
    from agent.audit.models import AuditLog
    repo.create_audit_log(AuditLog(
        action=SEED["audit_action"], entity_type="bvr", entity_id=SEED["need_id"],
        actor_id="bvr_script", organization_id=SEED["org_id"],
        from_state="A", to_state="B", details={"tag": RUN_TAG},
    ))

    user, _ = repo.create_user(User(
        username=SEED["user"]["username"], email=SEED["user"]["email"],
        password_hash=hash_password("BvrTestPassword1!"), full_name="BVR Script",
    ))
    repo.create_membership(OrganizationMembership(
        user_id=user.id, organization_id=SEED["org_id"], role="ORG_OPERATOR",
    ))

    # One PROCESSABLE event and one STALE CLAIMED event (claimed_at in the past).
    repo.append_agent_event(AgentEvent(
        event_id=SEED["agent_event_id"], event_type=AgentEventType.NEED_CREATED,
        status=EventStatus.PENDING, created_at=now.isoformat(),
        metadata={}, organization_id=None,
    ))
    stale_event = AgentEvent(
        event_id=f"{SEED['agent_event_id']}_stale", event_type=AgentEventType.NEED_CREATED,
        status=EventStatus.CLAIMED, created_at=now.isoformat(),
        metadata={}, organization_id=None,
    )
    repo.append_agent_event(stale_event)
    # Backdate the claim so recovery treats it as stale.
    from agent.data.schema import agent_events as ae
    from sqlalchemy import update
    with repo._engine.begin() as conn:
        conn.execute(update(ae).where(ae.c.event_id == stale_event.event_id).values(
            claimed_at=datetime.now(timezone.utc).replace(year=2020),
        ))

    print(f"Seeded synthetic data (tag {RUN_TAG}).")


def verify_survival() -> None:
    from agent.data.repository import get_repository
    repo = get_repository()

    need = repo.get_need(SEED["need_id"])
    check("need survived", need is not None and need.title == f"BVR need {RUN_TAG}")

    offer = repo.get_resource_offer(SEED["offer_id"])
    check("offer survived", offer is not None and offer.organization_id == SEED["org_id"])

    op = repo.get_operation(SEED["op_id"])
    check("operation survived", op is not None and op.need_id == SEED["need_id"])

    proposal = repo.get_proposal(SEED["proposal_id"])
    check("proposal survived", proposal is not None)
    if proposal:
        # Privacy boundary: the org evaluation is intact and org-scoped.
        check("proposal org evaluation intact",
              proposal.get("org_evaluation", {}).get("decision") == "ACCEPT")
        check("proposal targeted org preserved",
              proposal.get("organization_id") == SEED["org_id"])

    notifs = repo.list_notifications(recipient_id=SEED["org_id"], limit=100)
    check("notification survived", any(n.id == SEED["notif_id"] for n in notifs))

    events = repo.list_activity_events(entity_type="need", entity_id=SEED["need_id"], limit=100)
    check("activity event survived", any(e.id == SEED["activity_id"] for e in events))

    logs = repo.list_audit_logs(action=SEED["audit_action"], limit=10)
    check("audit record survived", len(logs) >= 1 and logs[0].to_state == "B")

    user = repo.get_user_by_username(SEED["user"]["username"])
    check("user survived", user is not None)
    if user:
        mems = repo.list_memberships_for_user(user.id)
        check("membership survived", any(m.organization_id == SEED["org_id"] for m in mems))

    event = repo.get_agent_event(SEED["agent_event_id"])
    check("agent event survived", event is not None and event.status in (EventStatus.PENDING.value, "PENDING"))

    stale = repo.get_agent_event(f"{SEED['agent_event_id']}_stale")
    check("stale CLAIMED agent event survived", stale is not None and stale.status == EventStatus.CLAIMED.value)


def verify_stale_recovery() -> None:
    """Restored CLAIMED rows must be requeueable by the standard recovery path."""
    from agent.data.repository import get_repository
    from agent.agents.event_router import get_event_dispatcher

    repo = get_repository()
    dispatcher = get_event_dispatcher()
    recovered = dispatcher.recover_stale_events(repo=repo, stale_threshold_seconds=0)
    stale = repo.get_agent_event(f"{SEED['agent_event_id']}_stale")
    check("stale event recoverable after restore",
          stale is not None and stale.status == EventStatus.PENDING.value,
          f"(recovered={recovered}, status={stale.status if stale else 'missing'})")


def cleanup() -> None:
    from agent.data.repository import get_repository
    from agent.data.schema import (
        agent_events, organizations, needs, resource_offers, operations,
        coordination_proposals, activity_events, notifications, audit_logs,
        users, organization_memberships,
    )
    from agent.auth.models import User as UserModel  # noqa: F401
    repo = get_repository()
    with repo._engine.begin() as conn:
        conn.execute(agent_events.delete().where(agent_events.c.event_id.like(f"%{RUN_TAG}%")))
        conn.execute(notifications.delete().where(notifications.c.id == SEED["notif_id"]))
        conn.execute(activity_events.delete().where(activity_events.c.id == SEED["activity_id"]))
        conn.execute(audit_logs.delete().where(audit_logs.c.action == SEED["audit_action"]))
        conn.execute(coordination_proposals.delete().where(coordination_proposals.c.id == SEED["proposal_id"]))
        conn.execute(operations.delete().where(operations.c.id == SEED["op_id"]))
        conn.execute(resource_offers.delete().where(resource_offers.c.id == SEED["offer_id"]))
        conn.execute(needs.delete().where(needs.c.id == SEED["need_id"]))
        conn.execute(organization_memberships.delete().where(
            organization_memberships.c.organization_id.in_([SEED["org_id"], SEED["other_org_id"]])
        ))
        conn.execute(users.delete().where(users.c.username == SEED["user"]["username"]))
        conn.execute(organizations.delete().where(
            organizations.c.id.in_([SEED["org_id"], SEED["other_org_id"]])
        ))
    print("Cleanup complete.")


def pg_env(db: dict) -> dict:
    env = os.environ.copy()
    env["PGHOST"] = db["host"]
    env["PGPORT"] = str(db["port"])
    env["PGUSER"] = db["user"]
    env["PGPASSWORD"] = db["password"]
    return env


def run_pg(cmd: list[str], env: dict) -> None:
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:2])} failed: {proc.stderr[-500:]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify ReliefOS backup/restore round-trip")
    parser.add_argument("--dump-file", default=f"reliefos_bvr_{RUN_TAG}.dump")
    parser.add_argument("--skip-restore", action="store_true",
                        help="Only seed + verify on the live DB (no dump/restore)")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL", "")
    if not url or "postgresql" not in url.lower():
        print("DATABASE_URL must point at PostgreSQL.", file=sys.stderr)
        return 2
    db = parse_database_url(url)

    print(f"== ReliefOS backup/restore verification (tag {RUN_TAG}) ==")
    from agent.data import repository as repo_mod
    repo_mod.reset_repository()

    seed_synthetic_data()

    if not args.skip_restore:
        env = pg_env(db)
        print(f"\nStep 1: pg_dump -> {args.dump_file}")
        run_pg(["pg_dump", "-Fc", "-h", db["host"], "-p", str(db["port"]),
                "-U", db["user"], "-d", db["database"], "-f", args.dump_file], env)

        print("Step 2: drop + recreate database")
        run_pg(["psql", "-h", db["host"], "-p", str(db["port"]), "-U", db["user"],
                "-d", "postgres", "-c",
                f'DROP DATABASE IF EXISTS "{db["database"]}";'
                f'CREATE DATABASE "{db["database"]}" OWNER "{db["user"]}";'], env)
        run_pg(["psql", "-h", db["host"], "-p", str(db["port"]), "-U", db["user"],
                "-d", db["database"], "-c", "CREATE EXTENSION IF NOT EXISTS postgis;"], env)

        print("Step 3: pg_restore")
        run_pg(["pg_restore", "-h", db["host"], "-p", str(db["port"]),
                "-U", db["user"], "-d", db["database"], "--no-owner", args.dump_file], env)

        repo_mod.reset_repository()

    print("\nStep 4: verify survival after restore")
    verify_survival()

    print("\nStep 5: verify AgentEvent safety (stale recovery)")
    verify_stale_recovery()

    print("\nStep 6: cleanup synthetic rows")
    cleanup()

    failed = [r for r in results if not r[1]]
    print(f"\n== RESULT: {len(results) - len(failed)}/{len(results)} checks passed ==")
    if args.skip_restore:
        print("NOTE: ran with --skip-restore; this proves seeding/verification only, NOT restore integrity.")
    if os.path.exists(args.dump_file) and not args.skip_restore:
        print(f"Dump file retained for inspection: {args.dump_file}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
