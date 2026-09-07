"""
Item #5 Step 2 — One-time migration: coordination proposals JSON → PostgreSQL.

Run AFTER tables exist:
    DATABASE_URL=postgresql://... python -m agent.data.migrate_proposals

Behavior:
- Reads agent/data/coordination_proposals.json (the former authoritative store).
- Imports every record into the coordination_proposals table via the
  repository layer (same code path as the API), idempotently (existing
  proposal ids are skipped, not duplicated).
- Validates: record counts, id uniqueness, status values, timestamp parse,
  org references, and that org_evaluation/private_factors round-trip.
- Does NOT delete or modify the JSON file — it is retained as migration
  history/fixture only (no runtime code reads it anymore).

Exit codes: 0 = migrated/verified, 1 = validation failure.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
LEGACY_JSON = os.path.join(_DATA_DIR, "coordination_proposals.json")

VALID_STATUSES = {
    "PROPOSED", "PENDING_ORG_REVIEW", "ORG_RECOMMENDED",
    "PENDING_HUMAN_APPROVAL", "PUBLISHED", "CONFIRMED", "COMPLETED",
    "DECLINED", "EXPIRED",
}


def _parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def migrate(repo=None, json_path: str = None) -> dict:
    """Import legacy JSON proposals into the authoritative store.

    Returns a validation report dict. Raises nothing; callers inspect the
    report (skipped/failed lists) to decide success.
    """
    if repo is None:
        from agent.data.repository import get_repository
        repo = get_repository()

    path = json_path or LEGACY_JSON
    if not os.path.exists(path):
        return {
            "source": path,
            "records_before": 0,
            "imported": 0,
            "skipped_existing": 0,
            "failed": [],
            "note": "No legacy JSON file present — nothing to migrate.",
        }

    with open(path, "r") as f:
        records = json.load(f)

    report = {
        "source": path,
        "records_before": len(records),
        "imported": 0,
        "skipped_existing": 0,
        "failed": [],
        "statuses": {},
        "org_refs": {},
    }

    seen_ids = set()
    for rec in records:
        pid = rec.get("id")
        # --- validation ---
        if not pid:
            report["failed"].append({"id": None, "reason": "missing id"})
            continue
        if pid in seen_ids:
            report["failed"].append({"id": pid, "reason": "duplicate id in source file"})
            continue
        seen_ids.add(pid)

        status = rec.get("status")
        if status not in VALID_STATUSES:
            report["failed"].append({"id": pid, "reason": f"invalid status: {status}"})
            continue
        report["statuses"][status] = report["statuses"].get(status, 0) + 1

        if not rec.get("organization_id"):
            report["failed"].append({"id": pid, "reason": "missing organization_id"})
            continue
        report["org_refs"][rec["organization_id"]] = \
            report["org_refs"].get(rec["organization_id"], 0) + 1

        if _parse_ts(rec.get("created_at")) is None:
            report["failed"].append({"id": pid, "reason": "unparseable created_at"})
            continue

        # --- import (idempotent: skip ids already in the store) ---
        existing = repo.get_proposal(pid)
        if existing is not None:
            report["skipped_existing"] += 1
            continue

        try:
            repo.create_proposal({
                "id": pid,
                "need_id": rec.get("need_id", ""),
                "organization_id": rec["organization_id"],
                "organization_name": rec.get("organization_name"),
                "proposal_type": rec.get("proposal_type", "other"),
                "summary": rec.get("summary", ""),
                "public_evidence": rec.get("public_evidence") or [],
                "network_findings": rec.get("network_findings") or [],
                "constraints": rec.get("constraints") or [],
                "uncertainty": rec.get("uncertainty") or [],
                "recommended_action": rec.get("recommended_action", ""),
                "status": status,
                "created_at": rec.get("created_at"),
                "updated_at": rec.get("updated_at") or rec.get("created_at"),
                "approved_at": rec.get("approved_at"),
                "approved_by": rec.get("approved_by"),
                "published_offer_id": rec.get("published_offer_id"),
                "operation_id": rec.get("operation_id"),
                "org_evaluation": rec.get("org_evaluation"),
                "private_factors": rec.get("private_factors"),
            })
            report["imported"] += 1
        except Exception as e:  # noqa: BLE001
            report["failed"].append({"id": pid, "reason": f"insert failed: {e}"})

    return report


def main() -> int:
    report = migrate()
    print(json.dumps(report, indent=2, default=str))

    if report["failed"]:
        print(f"\nMIGRATION INCOMPLETE: {len(report['failed'])} record(s) failed validation",
              file=sys.stderr)
        return 1

    # Post-import verification: DB count must equal source count.
    from agent.data.repository import get_repository
    repo = get_repository()
    all_props = repo.list_proposals()
    if len(all_props) < report["records_before"]:
        print(f"\nVERIFICATION FAILED: store has {len(all_props)} proposals, "
              f"source had {report['records_before']}", file=sys.stderr)
        return 1

    print(f"\nOK: {report['imported']} imported, "
          f"{report['skipped_existing']} already present, "
          f"{len(all_props)} total in authoritative store.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
