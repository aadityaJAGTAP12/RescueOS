"""
ReliefOS Smoke Cleanup — removes all synthetic data created by the smoke run.

Precise: deletes the exact entity ids recorded in the manifest (manifest["ids"]),
plus tagged fallbacks. File-backed private org workspaces
(data/orgs/<org_id>/) are deleted with shutil.
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from smoke_lib import load_manifest, child_env  # noqa: E402

m = load_manifest()
tag = m["tag"]
ids = m.get("ids", {})

os.environ.pop("RELIEFOS_MEMORY", None)
for k, v in child_env().items():
    os.environ.setdefault(k, v)

from agent.data.repository import get_repository  # noqa: E402

repo = get_repository()
print(f"cleanup with tag={tag} against {type(repo).__name__}")

# --- File-backed private workspace -----------------------------------------
for org_id in (m["org_alpha"], m["org_beta"]):
    org_dir = os.path.join(ROOT, "data", "orgs", org_id)
    if os.path.isdir(org_dir):
        shutil.rmtree(org_dir, ignore_errors=True)
        print(f"removed private workspace {org_id}")

# --- PostgreSQL rows ---------------------------------------------------------
if type(repo).__name__ != "PostgresRepository":
    print("cleanup skipped: not PostgreSQL")
    sys.exit(0)

from agent.data import schema as sch  # noqa: E402
from sqlalchemy import delete  # noqa: E402

total = 0


def _delete(table, column, values, label):
    global total
    values = [v for v in values if v]
    if not values:
        return
    with repo._engine.begin() as conn:
        res = conn.execute(delete(table).where(column.in_(values)))
        n = res.rowcount or 0
        total += n
        if n:
            print(f"  {label}: deleted {n}")


# 1. Precise id-based deletes (children first)
_delete(sch.organization_memberships, sch.organization_memberships.c.organization_id,
        [m["org_alpha"], m["org_beta"]], "memberships(org)")
_delete(sch.coordination_proposals, sch.coordination_proposals.c.id,
        ids.get("coordination_proposals", []), "proposals")
_delete(sch.operation_participants, sch.operation_participants.c.operation_id,
        ids.get("operations", []), "operation_participants")
_delete(sch.operations, sch.operations.c.id, ids.get("operations", []), "operations")
_delete(sch.resource_offers, sch.resource_offers.c.id,
        ids.get("resource_offers", []), "offers")
_delete(sch.activity_events, sch.activity_events.c.entity_id,
        ids.get("needs", []) + ids.get("operations", []) +
        ids.get("resource_offers", []) + ids.get("coordination_proposals", []),
        "activity_events")
_delete(sch.notifications, sch.notifications.c.entity_id,
        ids.get("needs", []) + ids.get("coordination_proposals", []),
        "notifications")
_delete(sch.agent_events, sch.agent_events.c.entity_id,
        [v.rstrip("%") for v in ids.get("agent_events", [])] +
        ids.get("needs", []), "agent_events")
_delete(sch.agent_events, sch.agent_events.c.id,
        [v for v in ids.get("agent_events", []) if not v.endswith("%")],
        "agent_events(by id)")
_delete(sch.needs, sch.needs.c.id, ids.get("needs", []), "needs")
_delete(sch.audit_logs, sch.audit_logs.c.id, ids.get("audit_logs", []), "audit_logs")

# 2. Tagged fallback sweep (catches anything not recorded precisely)
with repo._engine.begin() as conn:
    for table, col, label in (
        (sch.agent_events, sch.agent_events.c.id, "agent_events(tagged)"),
        (sch.needs, sch.needs.c.title, "needs(tagged)"),
        (sch.activity_events, sch.activity_events.c.detail, "activity(tagged)"),
    ):
        res = conn.execute(delete(table).where(col.like(f"%{tag}%")))
        n = res.rowcount or 0
        total += n
        if n:
            print(f"  {label}: deleted {n}")

# 2b. Org-scoped sweep: agent_events / audit_logs / notifications reference
# the smoke orgs via columns the tagged sweep cannot see.
with repo._engine.begin() as conn:
    for table, col, label in (
        (sch.agent_events, sch.agent_events.c.organization_id, "agent_events(org)"),
        (sch.audit_logs, sch.audit_logs.c.organization_id, "audit_logs(org)"),
        (sch.notifications, sch.notifications.c.recipient_id, "notifications(org)"),
    ):
        res = conn.execute(delete(table).where(col.in_([m["org_alpha"], m["org_beta"]])))
        n = res.rowcount or 0
        total += n
        if n:
            print(f"  {label}: deleted {n}")

# 2c. Final safety net: any remaining rows referencing the smoke orgs.
with repo._engine.begin() as conn:
    res = conn.execute(delete(sch.coordination_proposals).where(
        sch.coordination_proposals.c.organization_id.in_([m["org_alpha"], m["org_beta"]])))
    n = res.rowcount or 0
    total += n
    if n:
        print(f"  proposals(org): deleted {n}")

# 3. Users + orgs last (after membership rows are gone)
user_ids = [u["id"] for u in m["users"].values()]
with repo._engine.begin() as conn:
    for uid in user_ids:
        conn.execute(delete(sch.organization_memberships).where(
            sch.organization_memberships.c.user_id == uid))
_delete(sch.users, sch.users.c.id, user_ids, "users")
_delete(sch.organizations, sch.organizations.c.id,
        [m["org_alpha"], m["org_beta"]], "organizations")

print(f"cleanup deleted ~{total} rows")
print("cleanup complete")
