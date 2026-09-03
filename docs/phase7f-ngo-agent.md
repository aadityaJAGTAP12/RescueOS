# ReliefOS Phase 7F — NGO Main Agent + Organization Worker Agents

## Overview

Phase 7F implements the NGO Main Agent and its internal worker agents — the second level of the ReliefOS hierarchical AI architecture. The agent reasons over private organizational state + shared network state to produce recommendations that require human approval.

## Architecture

```
NGO Main Agent
├── PrivateOrganizationContext (NEVER exposed to network)
│   ├── Resources (available/committed/deployed)
│   ├── Teams (available/assigned/unavailable)
│   └── Missions (PLANNING/READY/ACTIVE/COMPLETED)
│
├── SharedNetworkContext (visible to all)
│   ├── Open Needs
│   ├── Active Operations
│   ├── Published Offers
│   └── Relevant Overrides
│
└── Output
    ├── Recommendation
    ├── Why (evidence-based)
    ├── Private Factors Used
    ├── Uncertainty
    ├── Proposed Publication (if applicable)
    └── Action Required
```

## What Was Built

### NGO Main Agent (`agent/agents/ngo_main_agent.py`)

**Core classes:**

| Class | Purpose |
|-------|---------|
| `PrivateOrganizationContext` | Private state: resources, teams, missions |
| `SharedNetworkContext` | Shared state: needs, operations, offers, overrides |
| `NGOMainAgent` | Main agent orchestrating analysis |

**Key methods:**

| Method | Purpose |
|--------|---------|
| `analyze_need(need, private_ctx, shared_ctx)` | Analyze a network Need with private context |
| `get_situation_summary(private_ctx, shared_ctx)` | Get organization situation overview |
| `_audit(action, details)` | Record audit event |

**Worker analysis (integrated into main agent):**

| Worker | Analysis |
|--------|----------|
| Inventory Worker | Available resources, committed resources, conflicts |
| Team Worker | Available teams, team status |
| Mission Worker | Active missions, resource conflicts |
| Logistics Worker | Route/access overrides |
| Field Worker | Field report relevance (via shared context) |

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/orgs/<id>/agent/analyze-need` | POST | Analyze a Need with private context |
| `/api/orgs/<id>/agent/situation` | GET | Get organization situation summary |

### Frontend: NGO Agent Panel

Added to OrganizationWorkspace as "AI" tab:

- **Situation Summary** — Private resources, teams, missions + network needs
- **Attention Items** — Proactive alerts (unused resources, conflicts)
- **Quick Analysis** — Select a network need to analyze
- **Analysis Result** — Recommendation, why, private factors, uncertainty
- **Proposed Publication** — Review and publish offer workflow

## Privacy Boundary

**PRIVATE** (never exposed to network):
- `PrivateOrganizationContext` — resources, teams, missions
- Stored in `data/orgs/{org_id}/` (isolated per org)
- Only accessible via `/api/orgs/<id>/...` endpoints

**PUBLIC** (shared with network):
- Published Resource Offers
- Active Operations
- Organization Profile

**Publication workflow:**
1. NGO AI analyzes need using private context
2. AI proposes publication (resource type, quantity, location)
3. Human reviews proposed publication
4. Human clicks "PUBLISH OFFER"
5. Existing Resource Offer API creates public offer
6. Private resource status updates to "committed"

## Human Approval

The NGO Main Agent **NEVER** autonomously:
- Publishes a resource
- Commits a resource
- Assigns a team
- Starts a mission
- Accepts an operation
- Promises a delivery

Instead:
```
AI proposes → human reviews → human confirms → backend performs action
```

## LLM Fallback

The NGO workspace continues working if the LLM is unavailable:

- **Deterministic analysis** based on private/shared context
- Resource availability checks
- Conflict detection
- Simple rule-based recommendations
- Explicit "AI unavailable" indicator

## Auditability

Every agent action is recorded:
```json
{
  "timestamp": "2026-09-01T...",
  "org_id": "org_demo",
  "action": "analyze_need",
  "details": {"need_id": "need_1", "recommendation": "...", "action_required": "review"}
}
```

Raw private reasoning is NOT logged. Only operational rationale.

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| agent/agents/ngo_main_agent.py | New | NGO Main Agent with worker analysis |
| agent/api.py | Enhanced | +2 agent endpoints |
| frontend/src/components/workspace/OrganizationWorkspace.jsx | Enhanced | +NGO Agent Panel |
| tests/test_ngo_agent.py | New | 13 tests for agent privacy and functionality |
| docs/phase7f-ngo-agent.md | New | This documentation |

## Tests

**New tests (test_ngo_agent.py):**
- Private context: available resources, teams, missions, conflicts
- Need analysis: with resources, no resources, conflicts
- Situation summary: private + network state
- Privacy boundary: private not in shared, publication subset
- Auditability: actions recorded

**All existing tests:** 103 passed (unchanged)
**New NGO agent tests:** 13 passed
**Total: 116 passed, 0 failed**

## Verification

```
Frontend build: ✅ (612KB JS, 51KB CSS)
Backend tests: ✅ (116 passed)
DATABASE MODIFIED: NO
DOCKER MODIFIED: NO
FLOOD DATA MODIFIED: NO
OSM DATA MODIFIED: NO
PRIVATE NGO DATA MODIFIED: NO (JSON file storage only)
```

## Future Network ↔ NGO Agent Interface

When AI-to-AI negotiation is implemented:

```
Network Main Agent: "Need #1042 is seeking 2 boats."
    ↓
NGO Main Agent: "We can potentially offer 1 boat."
    ↓
Network: "Potential organization capability received."
    ↓
Human: [ APPROVE ]
    ↓
Resource Offer → Match → Operation
```

This interface is architecturally ready but NOT implemented in Phase 7F.

## What Was NOT Implemented (Deferred)

- Autonomous AI-to-AI negotiation
- Automatic resource publication
- Autonomous team assignment
- Cross-org private data access
- Complex RBAC
- WebSocket migration
- Mobile app
- Predictive resource demand model
