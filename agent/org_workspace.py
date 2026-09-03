"""
ReliefOS Organization Workspace — Private Organizational State

Phase 7E: Private resource inventory, teams, and missions for NGOs.

Design principles:
- PRIVATE: inventory, teams, missions, commitments stay private
- PUBLIC: published offers, operations, profile are shared with network
- Human chooses what to publish — no automatic publication
- Minimal model: only what's needed for the workspace
- JSON file storage (same pattern as community_reports, overrides)
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
ORG_DIR = os.path.join(_DATA_DIR, "orgs")


def _ensure_org_dir(org_id: str) -> str:
    """Ensure the org directory exists and return its path."""
    org_dir = os.path.join(ORG_DIR, org_id)
    os.makedirs(org_dir, exist_ok=True)
    return org_dir


def _org_file(org_id: str, filename: str) -> str:
    """Get the path to an org-specific file."""
    return os.path.join(_ensure_org_dir(org_id), filename)


def _load_json(filepath: str, default=None):
    """Load JSON from file, returning default if missing/invalid."""
    if not os.path.exists(filepath):
        return default if default is not None else []
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []


def _save_json(filepath: str, data) -> None:
    """Save data to JSON file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Private Resource Inventory
# ---------------------------------------------------------------------------

def list_resources(org_id: str) -> list[dict]:
    """List all private resources for an organization."""
    return _load_json(_org_file(org_id, "resources.json"), [])


def add_resource(org_id: str, resource: dict) -> dict:
    """Add a new private resource to the organization inventory."""
    resource["id"] = resource.get("id", f"res_{str(uuid.uuid4())[:8]}")
    resource["org_id"] = org_id
    resource["created_at"] = resource.get("created_at", datetime.now(timezone.utc).isoformat())
    resource["updated_at"] = datetime.now(timezone.utc).isoformat()
    resource["status"] = resource.get("status", "available")  # available|committed|unavailable|in_transit|deployed

    resources = list_resources(org_id)
    resources.append(resource)
    _save_json(_org_file(org_id, "resources.json"), resources)
    return resource


def update_resource(org_id: str, resource_id: str, updates: dict) -> Optional[dict]:
    """Update a private resource."""
    resources = list_resources(org_id)
    for r in resources:
        if r["id"] == resource_id:
            r.update(updates)
            r["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_json(_org_file(org_id, "resources.json"), resources)
            return r
    return None


def delete_resource(org_id: str, resource_id: str) -> bool:
    """Delete a private resource."""
    resources = list_resources(org_id)
    new_resources = [r for r in resources if r["id"] != resource_id]
    if len(new_resources) < len(resources):
        _save_json(_org_file(org_id, "resources.json"), new_resources)
        return True
    return False


# ---------------------------------------------------------------------------
# Private Teams
# ---------------------------------------------------------------------------

def list_teams(org_id: str) -> list[dict]:
    """List all private teams for an organization."""
    return _load_json(_org_file(org_id, "teams.json"), [])


def add_team(org_id: str, team: dict) -> dict:
    """Add a new private team."""
    team["id"] = team.get("id", f"team_{str(uuid.uuid4())[:8]}")
    team["org_id"] = org_id
    team["created_at"] = team.get("created_at", datetime.now(timezone.utc).isoformat())
    team["updated_at"] = datetime.now(timezone.utc).isoformat()
    team["status"] = team.get("status", "available")  # available|assigned|unavailable
    team["members"] = team.get("members", [])
    team["current_assignment"] = team.get("current_assignment", None)
    team["location"] = team.get("location", None)

    teams = list_teams(org_id)
    teams.append(team)
    _save_json(_org_file(org_id, "teams.json"), teams)
    return team


def update_team(org_id: str, team_id: str, updates: dict) -> Optional[dict]:
    """Update a private team."""
    teams = list_teams(org_id)
    for t in teams:
        if t["id"] == team_id:
            t.update(updates)
            t["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_json(_org_file(org_id, "teams.json"), teams)
            return t
    return None


# ---------------------------------------------------------------------------
# Private Missions
# ---------------------------------------------------------------------------

def list_missions(org_id: str) -> list[dict]:
    """List all private missions for an organization."""
    return _load_json(_org_file(org_id, "missions.json"), [])


def add_mission(org_id: str, mission: dict) -> dict:
    """Add a new private mission."""
    mission["id"] = mission.get("id", f"mis_{str(uuid.uuid4())[:8]}")
    mission["org_id"] = org_id
    mission["created_at"] = mission.get("created_at", datetime.now(timezone.utc).isoformat())
    mission["updated_at"] = datetime.now(timezone.utc).isoformat()
    mission["status"] = mission.get("status", "PLANNING")  # PLANNING|READY|ACTIVE|COMPLETED
    mission["linked_need_id"] = mission.get("linked_need_id", None)
    mission["assigned_team_id"] = mission.get("assigned_team_id", None)
    mission["assigned_resources"] = mission.get("assigned_resources", [])
    mission["notes"] = mission.get("notes", "")

    missions = list_missions(org_id)
    missions.append(mission)
    _save_json(_org_file(org_id, "missions.json"), missions)
    return mission


def update_mission(org_id: str, mission_id: str, updates: dict) -> Optional[dict]:
    """Update a private mission."""
    missions = list_missions(org_id)
    for m in missions:
        if m["id"] == mission_id:
            m.update(updates)
            m["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_json(_org_file(org_id, "missions.json"), missions)
            return m
    return None


# ---------------------------------------------------------------------------
# Organization Summary
# ---------------------------------------------------------------------------

def get_org_summary(org_id: str, repo=None) -> dict:
    """
    Get a summary of the organization's private and public state.

    Returns:
        {
            "org_id": str,
            "profile": {...},
            "private": {
                "resources": [...],
                "teams": [...],
                "missions": [...],
            },
            "public": {
                "published_offers": [...],
                "active_operations": [...],
            },
            "network_requests": [...],
        }
    """
    if repo is None:
        from agent.data.repository import get_repository
        repo = get_repository()

    # Profile
    org = repo.get_organization(org_id) if hasattr(repo, 'get_organization') else None
    profile = org.to_dict() if org else {"id": org_id, "name": org_id}

    # Private state
    resources = list_resources(org_id)
    teams = list_teams(org_id)
    missions = list_missions(org_id)

    # Compute summary stats
    available_resources = [r for r in resources if r.get("status") == "available"]
    committed_resources = [r for r in resources if r.get("status") == "committed"]
    deployed_resources = [r for r in resources if r.get("status") == "deployed"]
    available_teams = [t for t in teams if t.get("status") == "available"]
    active_missions = [m for m in missions if m.get("status") in ("ACTIVE", "READY")]

    # Public state
    try:
        all_offers = repo.list_resource_offers(organization_id=org_id) if hasattr(repo, 'list_resource_offers') else []
        published_offers = [o.to_dict() for o in all_offers if o.status != "WITHDRAWN"]
    except Exception:
        published_offers = []

    try:
        all_ops = repo.list_operations() if hasattr(repo, 'list_operations') else []
        active_operations = [o.to_dict() for o in all_ops
                           if o.lead_organization_id == org_id and o.status in ("PLANNING", "ACTIVE")]
    except Exception:
        active_operations = []

    # Network requests (open needs)
    try:
        open_needs = repo.list_needs(status="OPEN") if hasattr(repo, 'list_needs') else []
        network_requests = [n.to_dict() for n in open_needs]
    except Exception:
        network_requests = []

    return {
        "org_id": org_id,
        "profile": profile,
        "summary": {
            "total_resources": len(resources),
            "available_resources": len(available_resources),
            "committed_resources": len(committed_resources),
            "deployed_resources": len(deployed_resources),
            "total_teams": len(teams),
            "available_teams": len(available_teams),
            "active_missions": len(active_missions),
            "published_offers": len(published_offers),
            "active_operations": len(active_operations),
            "network_requests": len(network_requests),
        },
        "private": {
            "resources": resources,
            "teams": teams,
            "missions": missions,
        },
        "public": {
            "published_offers": published_offers,
            "active_operations": active_operations,
        },
        "network_requests": network_requests,
    }
