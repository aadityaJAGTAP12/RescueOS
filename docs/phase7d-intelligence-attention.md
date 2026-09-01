# ReliefOS Phase 7D — Intelligence + Attention System

## Overview

Phase 7D makes ReliefOS capable of showing coordinators WHAT CHANGED, WHY IT MATTERS, WHAT EVIDENCE SUPPORTS IT, and WHICH REPORTS REPRESENT THE SAME REAL-WORLD EVENT. This is the Crucix-inspired attention layer adapted for humanitarian operations.

## Architecture

```
Delta Engine (agent/delta.py)
├── compute_delta()          — What changed in the operational state
├── deduplicate_reports()    — Semantic grouping of similar reports
└── synthesize_evidence()    — Evidence traceability for entities

API Endpoints
├── GET /api/delta           — Delta computation (hours param)
└── GET /api/evidence/<type>/<id> — Entity evidence synthesis

Frontend
├── ActivityBar              — Delta stream with directional indicators
├── WorkspaceHeader          — Temporal context controls (CURRENT/24H/7D)
├── ContextPanel             — Evidence/uncertainty/data-gap sections
└── workspaceContext         — Delta state management
```

## What Was Built

### Delta Engine (agent/delta.py)

**New module** providing:

1. **Delta Computation** — Computes what changed in the operational state over a configurable lookback period (default 24 hours)
2. **Semantic Report Deduplication** — Groups similar field reports into deduplicated events
3. **Evidence Synthesis** — Traces evidence for specific operational entities

**Delta Summary includes:**
- `new_needs`, `resolved_needs`, `escalated_needs`
- `new_offers`, `new_operations`, `new_reports`, `new_overrides`
- `total_active_needs`, `total_active_operations`, `total_open_offers`

**Directional indicators:**
- `access`: up/down/stable (road state changes)
- `resource_gap`: up/down/stable (new needs vs new offers)
- `response`: up/down/stable (new operations vs resolved needs)
- `unresolved`: up/down/stable (new needs vs resolved needs)

### Semantic Report Deduplication

Groups field reports that describe the same real-world event using:

1. **Spatial proximity** — Within 5km radius
2. **Temporal proximity** — Within 6 hours
3. **Text similarity** — Normalized text matching
4. **Category matching** — Same needs categories

**Real-world example from development data:**
```
BEFORE: 7 separate "Road blocked near Jorhat due to flooding" reports
AFTER:  1 grouped event with 7 reports, 0 verified
```

**Grouped event includes:**
- `event_id`, `title`, `category`
- `report_count`, `verified_count`
- `first_report`, `last_report` timestamps
- Individual `reports` array (preserving source data)
- `location_description`, `needs`, `people_count_max`
- `confidence` level

**Safety:** Reports without coordinates are grouped by exact text match only (no false spatial grouping).

### API Endpoints

| Endpoint | Method | Purpose | Parameters |
|----------|--------|---------|------------|
| `/api/delta` | GET | Compute delta | `hours` (default 24) |
| `/api/evidence/<type>/<id>` | GET | Synthesize evidence | entity type + id |

**Delta response:**
```json
{
  "generated_at": "2026-09-01T...",
  "lookback_hours": 24,
  "summary": { "new_needs": 2, "resolved_needs": 1, ... },
  "directional": { "resource_gap": "up", "response": "stable", ... },
  "events": [...],
  "grouped_reports": [...],
  "evidence_summary": { "field_reports_total": 11, "active_overrides": 8, ... }
}
```

**Evidence response:**
```json
{
  "entity_type": "need",
  "entity_id": "need_abc123",
  "evidence_items": [...],
  "uncertainty": [...],
  "data_gaps": [...],
  "confidence": "medium"
}
```

### Enhanced ActivityBar

**Before Phase 7D:**
- Simple event list with severity coloring
- Basic delta summary (counts only)

**After Phase 7D:**
- Time selector: 1H / 6H / 24H / 7D
- Directional indicators: GAP ↑/↓, RESP ↑/↓
- Grouped reports displayed as deduplicated events
- Escalation counter (↑)
- Group count indicator

### Enhanced WorkspaceHeader

**Temporal context controls:**
- CURRENT — Real-time view
- 24H — Last 24 hours delta
- 7D — Last 7 days delta

Time selection triggers delta fetch with appropriate lookback period.

### Enhanced ContextPanel Dossiers

**New EvidenceSection component** added to NeedDetail and OperationDetail:

- **Evidence items** — Source, timestamp, verification status, type
- **Uncertainty** — What we don't know (amber styling)
- **Data gaps** — What information is missing
- **Confidence** — High/medium/low badge

Each evidence item shows:
- `type` (field_report, operation, override)
- `detail` (human-readable description)
- `source` (who reported)
- `timestamp` (when)
- `verified` (if applicable)

### Severity Model

```
CRITICAL  → #dc2626 (red)     → AI recommendation, coordination gap
URGENT    → #d97706 (amber)   → need created, status changed, override
STABLE    → #16a34a (green)   → need resolved, resource offered
INFORMATION → #2563eb (blue)  → operation update, field update
```

Always uses icon + text + color (never color alone).

## Delta Sources

| Source | Delta Type | Data Available |
|--------|-----------|----------------|
| Activity events | new/resolved/updated | event_type, entity_type, timestamp |
| Needs | new/open/resolved | status, urgency, created_at |
| Operations | new/active/completed | status, need_id, created_at |
| Offers | new/accepted | status, resource_type, created_at |
| Field reports | new/grouped | timestamp, needs, verified |
| Overrides | new/active | target_type, override_status, timestamp |
| Flood snapshots | available | district, observed_at, provenance |

## Alert Fatigue Suppression

**Semantic deduplication prevents repeated alerts:**
- 7 identical "Road blocked near Jorhat" → 1 grouped event
- Individual reports remain accessible
- Group shows report count and verification status

**Escalation is NOT suppressed:**
- New severity → new attention item
- Material operational change → new alert
- Same report with new impact → new alert

## Evidence Model

**Three distinct concepts:**

1. **EVIDENCE** — What we know (field reports, overrides, operations)
2. **UNCERTAINTY** — What we're not sure about (stale data, proxy assessments)
3. **DATA GAP** — What we don't have (missing road status, no field confirmation)

These are never merged in the UI.

## Temporal Behavior

- CURRENT: Real-time view (default)
- 24H: Delta computed over last 24 hours
- 7D: Delta computed over last 7 days
- Flood snapshots: Real observed dates shown, no interpolation
- "Two snapshots available for this district" — honest about discrete observations

## AI Coordinator Integration

The AI coordinator now has access to:
- Delta summary (what changed)
- Directional indicators (trends)
- Grouped reports (deduplicated events)
- Evidence synthesis (traceability)

AI findings reference:
- Specific needs/operations via `review_target`
- Evidence items supporting the finding
- Uncertainty about the finding
- Data gaps relevant to the finding

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| agent/delta.py | New | Delta engine, deduplication, evidence synthesis |
| agent/api.py | Enhanced | +/api/delta, +/api/evidence endpoints |
| frontend/src/lib/workspaceContext.jsx | Enhanced | +delta state, +fetchDelta |
| frontend/src/components/workspace/ActivityBar.jsx | Rewritten | +time selector, +directional indicators, +grouped reports |
| frontend/src/components/workspace/WorkspaceHeader.jsx | Enhanced | +temporal context controls |
| frontend/src/components/workspace/ContextPanel.jsx | Enhanced | +EvidenceSection component, +evidence in NeedDetail/OperationDetail |
| tests/test_delta.py | New | 15 tests for delta engine |
| docs/phase7d-intelligence-attention.md | New | This documentation |

## Tests

**New tests (test_delta.py):**
- Delta computation: empty repo, new needs, resolved needs, directional indicators
- Report deduplication: empty, single, identical grouping, different reports, verified count
- Evidence synthesis: need with no data, operation evidence
- Helpers: text normalization, temporal proximity, need categorization

**All existing tests:** 88 passed (unchanged)
**New delta tests:** 15 passed
**Total: 103 passed, 0 failed**

## Verification

```
Frontend build: ✅ (588KB JS, 50KB CSS)
Backend tests: ✅ (103 passed)
DATABASE MODIFIED: NO
DOCKER MODIFIED: NO
FLOOD DATA MODIFIED: NO
OSM DATA MODIFIED: NO
```

## What Was NOT Changed

- Database schema
- Flood/OSM data
- Docker configuration
- Agent/planner architecture
- Matching engine
- Data models
- Community reports storage
- Override storage
