# ReliefOS Phase 7G — Network Main Agent + Hierarchical Network Coordination

## Overview

Phase 7G implements the Network Main Agent — the network-side counterpart to the NGO Main Agent. It reasons over the shared emergency operating picture and coordinates with NGO Main Agents WITHOUT accessing private NGO state.

## Architecture

```
Network Main Agent
├── Situation/Flood Worker  — flood state, temporal analysis
├── Exposure Worker         — affected settlements, buildings, infrastructure
├── Medical Worker          — health risks, facility access
├── Logistics Worker        — resource matching, coordination gaps
├── Access/Routing Worker   — road/bridge status, overrides
├── Field Intelligence Worker — field reports, deduplication
├── Coordination Worker     — uncovered needs, surplus offers
└── Evidence Worker         — evidence synthesis, uncertainty
```

Each worker returns structured findings:
```json
{
  "worker": "name",
  "findings": [...],
  "evidence": [...],
  "uncertainty": [...],
  "data_gaps": [...],
  "recommendations": [...]
}
```

## What Was Built

### Worker Modules (`agent/agents/network_workers/`)

| Worker | Module | Purpose |
|--------|--------|---------|
| Situation/Flood | `situation.py` | Flood state, temporal analysis, district coverage |
| Exposure | `exposure.py` | Affected settlements, infrastructure exposure |
| Medical | `medical.py` | Health risks, facility access (cautious language) |
| Logistics | `logistics.py` | Resource matching, coordination gaps |
| Access/Routing | `access.py` | Road/bridge status, overrides, routing |
| Field Intelligence | `field.py` | Field reports, deduplication, verification |
| Coordination | `coordination.py` | Uncovered needs, surplus offers, pairings |
| Evidence | `evidence.py` | Evidence synthesis, uncertainty |

### Network Main Agent (`agent/agents/network_main_agent.py`)

**Core class:** `NetworkMainAgent`

**Key methods:**
- `analyze_network(repo)` — Full network analysis using all workers
- `analyze_need_context(need, repo)` — Analyze specific need in network context
- `_audit(action, details)` — Record audit event

**Output structure:**
```json
{
  "generated_at": "...",
  "summary": "...",
  "situation": [...],
  "priority_needs": [...],
  "coordination_opportunities": [...],
  "risks": [...],
  "worker_findings": {...},
  "evidence": [...],
  "uncertainty": [...],
  "data_gaps": [...],
  "recommended_actions": [...],
  "severity_summary": {"critical": N, "urgent": N, ...}
}
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/network/agent/analyze` | GET | Full network analysis |
| `/api/network/agent/analyze-need` | POST | Analyze specific need |
| `/api/network/agent/situation` | GET | Situation summary |

### Frontend: Network Agent Section

Added to AIAnalysisPanel in ContextPanel:
- Collapsible "Network Agent" section
- Summary text
- Priority needs (with severity)
- Risks
- Recommended actions
- Severity badges

## Privacy Boundary

**PRIVATE** (never accessed by Network Agent):
- NGO inventory, teams, missions
- `data/orgs/{org_id}/` files
- Private organizational state

**PUBLIC** (accessible by Network Agent):
- Published Resource Offers
- Active Operations
- Open Needs
- Field Reports
- Overrides
- Flood Snapshots
- Road/Bridge Status

**Correct flow:**
```
NGO private state → NGO Main Agent → human approval → published offer → Network Agent
```

**Incorrect flow:**
```
Network Agent → raw NGO inventory (NEVER)
```

## Worker Responsibilities

| Worker | Answers | Does NOT |
|--------|---------|----------|
| Situation | What areas are affected? What changed? | Invent flood progression |
| Exposure | Which infrastructure is at risk? | Claim damage without evidence |
| Medical | What health risks exist? | Claim outbreaks without evidence |
| Logistics | What are the coordination gaps? | Commit resources |
| Access | What routes are viable? | Pretend routing is valid when unknown |
| Field | What do reports indicate? | Treat all reports as verified |
| Coordination | What needs coverage? | Auto-assign organizations |
| Evidence | What supports each finding? | Fabricate confidence |

## Human Approval

The Network Main Agent **NEVER** autonomously:
- Commits resources
- Deploys organizations
- Creates operations
- Assigns teams
- Promises deliveries

All recommendations are proposals requiring human action.

## LLM Fallback

The Network Agent works without an LLM:
- Deterministic worker analysis
- Rule-based prioritization
- Existing tool capabilities
- Explicit "AI unavailable" indicators

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| agent/agents/network_workers/__init__.py | New | Workers package |
| agent/agents/network_workers/situation.py | New | Situation/Flood Worker |
| agent/agents/network_workers/exposure.py | New | Exposure Worker |
| agent/agents/network_workers/medical.py | New | Medical Worker |
| agent/agents/network_workers/logistics.py | New | Logistics Worker |
| agent/agents/network_workers/access.py | New | Access/Routing Worker |
| agent/agents/network_workers/field.py | New | Field Intelligence Worker |
| agent/agents/network_workers/coordination.py | New | Coordination Worker |
| agent/agents/network_workers/evidence.py | New | Evidence Worker |
| agent/agents/network_main_agent.py | New | Network Main Agent |
| agent/api.py | Enhanced | +3 network agent endpoints |
| frontend/src/components/workspace/ContextPanel.jsx | Enhanced | +NetworkAgentSection |
| tests/test_network_agent.py | New | 15 tests |
| docs/phase7g-network-agent.md | New | This documentation |

## Tests

**New tests (test_network_agent.py):**
- Worker initialization and structured output
- Network agent analysis (empty + with data)
- Need context analysis
- No private state leakage
- Deterministic operation (no LLM)
- Audit logging

**All existing tests:** 116 passed (unchanged)
**New network agent tests:** 15 passed
**Total: 131 passed, 0 failed**

## Verification

```
Frontend build: ✅ (615KB JS, 51KB CSS)
Backend tests: ✅ (131 passed)
DATABASE MODIFIED: NO
DOCKER MODIFIED: NO
FLOOD DATA MODIFIED: NO
OSM DATA MODIFIED: NO
PRIVATE NGO DATA MODIFIED: NO
```

## Future Network ↔ NGO Agent Interface

When AI-to-AI negotiation is implemented:
```
Network Main Agent: "Need #1042 is seeking 2 boats."
    ↓
NGO Main Agent: "We can potentially offer 1 boat."
    ↓
Human: [ APPROVE ]
    ↓
Resource Offer → Match → Operation
```

This interface is architecturally ready but NOT implemented in Phase 7G.

## What Was NOT Implemented (Deferred)

- Autonomous AI-to-AI negotiation
- Autonomous resource matching
- Autonomous deployment
- WebSocket infrastructure
- New database migrations
- Major visual redesign
- Replacing the existing planner
