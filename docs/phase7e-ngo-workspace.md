# ReliefOS Phase 7E — NGO Workspace + Private Organizational State

## Overview

Phase 7E establishes the private NGO/organization workspace with a clean public/private boundary. Organizations can manage private resources, teams, and missions, then explicitly publish offers to the shared ReliefOS Network.

## Architecture

```
[ NETWORK ] ←→ [ MY ORGANIZATION ]
     │                │
     ▼                ▼
Shared State    Private Org State
     │                │
     │    ┌───────────┤
     │    │           │
     ▼    ▼           ▼
Needs  Operations  Resources
Offers Activity    Teams
                Missions
                     │
                     ▼
              Human Publishes
                     │
                     ▼
              Public Offer → Network
```

## What Was Built

### Backend: Private Organization Workspace (agent/org_workspace.py)

**New module** providing JSON-file-based private state:

| Function | Purpose |
|----------|---------|
| `list_resources(org_id)` | List private resource inventory |
| `add_resource(org_id, resource)` | Add resource to inventory |
| `update_resource(org_id, resource_id, updates)` | Update resource status |
| `delete_resource(org_id, resource_id)` | Remove resource |
| `list_teams(org_id)` | List private teams |
| `add_team(org_id, team)` | Add team |
| `update_team(org_id, team_id, updates)` | Update team |
| `list_missions(org_id)` | List private missions |
| `add_mission(org_id, mission)` | Add mission |
| `update_mission(org_id, mission_id, updates)` | Update mission |
| `get_org_summary(org_id)` | Full org summary (private + public) |

**Storage:** `data/orgs/{org_id}/resources.json`, `teams.json`, `missions.json`

### Backend: API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/orgs/<org_id>/summary` | GET | Full org summary |
| `/api/orgs/<org_id>/resources` | GET | List private resources |
| `/api/orgs/<org_id>/resources` | POST | Add private resource |
| `/api/orgs/<org_id>/resources/<id>` | PATCH | Update resource |
| `/api/orgs/<org_id>/resources/<id>` | DELETE | Delete resource |
| `/api/orgs/<org_id>/teams` | GET | List private teams |
| `/api/orgs/<org_id>/teams` | POST | Add private team |
| `/api/orgs/<org_id>/teams/<id>` | PATCH | Update team |
| `/api/orgs/<org_id>/missions` | GET | List private missions |
| `/api/orgs/<org_id>/missions` | POST | Add private mission |
| `/api/orgs/<org_id>/missions/<id>` | PATCH | Update mission |
| `/api/orgs/<org_id>/publish-offer` | POST | Publish offer to network |

### Frontend: Mode Toggle

**WorkspaceHeader** now includes:
```
[ Globe Network ] [ Shield My Org ]
```

Clicking toggles between NETWORK and ORGANIZATION views.

### Frontend: Organization Workspace (OrganizationWorkspace.jsx)

**New component** with tabbed interface:

| Tab | Content |
|-----|---------|
| Overview | Summary cards (resources, teams, missions, offers, operations, network requests) |
| Resources | Private resource inventory with add/update/status management |
| Teams | Private team list with status and member counts |
| Missions | Private mission list with status and linked needs |
| Requests | Network open needs that the organization can respond to |

### Private/Public Boundary

**PRIVATE** (never exposed to network):
- Resource inventory
- Team details
- Internal missions
- Private notes

**PUBLIC** (shared with network):
- Published resource offers
- Active operations
- Organization profile

**Publication workflow:**
1. User reviews private resources
2. User selects resource to publish
3. User creates public Resource Offer
4. Offer appears in shared network
5. Private resource status updates to "committed"

## Resource Status Model

| Status | Meaning | Color |
|--------|---------|-------|
| `available` | Ready to deploy | Green |
| `committed` | Allocated to operation | Amber |
| `deployed` | In field | Blue |
| `in_transit` | Moving to location | Teal |
| `unavailable` | Not usable | Gray |

## Team Status Model

| Status | Meaning |
|--------|---------|
| `available` | Ready for assignment |
| `assigned` | Currently on mission |
| `unavailable` | Not deployable |

## Mission Status Model

| Status | Meaning |
|--------|---------|
| `PLANNING` | Being planned |
| `READY` | Ready to execute |
| `ACTIVE` | Currently executing |
| `COMPLETED` | Finished |

## Network Request Flow

1. Organization switches to MY ORGANIZATION mode
2. Sees open network needs in "Requests" tab
3. Clicks need to review details (opens ContextPanel)
4. Evaluates using private resource/team information
5. Creates public Resource Offer if response is possible
6. Existing matching system picks up the offer
7. Match confirmation creates Operation
8. Organization sees Operation in "My Operations"

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| agent/org_workspace.py | New | Private org state models and storage |
| agent/api.py | Enhanced | +12 org workspace endpoints |
| frontend/src/components/workspace/OrganizationWorkspace.jsx | New | Full org workspace UI |
| frontend/src/components/workspace/NetworkWorkspace.jsx | Enhanced | Mode toggle support |
| frontend/src/components/workspace/WorkspaceHeader.jsx | Enhanced | Network/Org mode toggle |
| docs/phase7e-ngo-workspace.md | New | This documentation |

## Privacy Enforcement

- Private resources stored in `data/orgs/{org_id}/` (isolated per org)
- `/api/orgs/<id>/resources` only returns that org's data
- `/api/offers` only shows published offers (not private inventory)
- Organization profile only shows public information
- No cross-org data leakage in API responses

## Empty States

- **No private resources:** "Add resources to your inventory"
- **No private teams:** "No private teams"
- **No active missions:** "No active missions"
- **No open needs:** "All network requests are covered"

## Tests

All existing tests pass (103 passed).
New org workspace uses JSON file storage (same pattern as community_reports, overrides).

## Verification

```
Frontend build: ✅ (605KB JS, 50KB CSS)
Backend tests: ✅ (103 passed)
DATABASE MODIFIED: NO
DOCKER MODIFIED: NO
FLOOD DATA MODIFIED: NO
OSM DATA MODIFIED: NO
```

## What Was NOT Implemented (Deferred)

- NGO Main Agent
- NGO worker agents
- Autonomous organization decisions
- AI-to-AI negotiation
- Automatic resource publication
- Advanced RBAC/permissions
- Real-time individual tracking
- Email/SMS notifications
- Mobile app
- Full offline synchronization
