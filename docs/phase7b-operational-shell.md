# ReliefOS Phase 7B — Operational Shell

## Overview

Phase 7B implements the unified operational console: a persistent map-first workspace with contextual panels, AI coordinator integration, command search, and delta-based activity tracking. The implementation recomposes existing components into the final target shell architecture.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ WorkspaceHeader                                                  │
│  ReliefOS | District | Time | Live | AI | Notifications | ⌘K   │
├──────────┬──────────────────────────────────┬───────────────────┤
│          │                                   │                   │
│ LayerRail│         MapCanvas                 │ ContextPanel      │
│          │     (Leaflet/React-Leaflet)       │                   │
│ HAZARD   │                                   │ Selected object   │
│ INFRA    │     Persistent operational map    │ OR                │
│ RESPONSE │     with all active layers        │ AI Coordinator    │
│ INTEL    │                                   │                   │
│          │                                   │ Dossier views:    │
│ ACTIONS  │                                   │ Need, Operation,  │
│          │                                   │ Offer, Report,    │
│          │                                   │ Facility, Road,   │
│          │                                   │ Settlement        │
├──────────┴──────────────────────────────────┴───────────────────┤
│ ActivityBar — What Changed / Delta stream / Live status         │
└─────────────────────────────────────────────────────────────────┘
```

## Components Reused

| Component | File | Status |
|-----------|------|--------|
| NetworkWorkspace | NetworkWorkspace.jsx | Reused — layout shell |
| MapCanvas | MapCanvas.jsx | Reused — Leaflet map with all layers |
| ContextPanel | ContextPanel.jsx | Refactored — removed duplicate blocks, wired AI |
| LayerRail | LayerRail.jsx | Refactored — reorganized into target groups |
| WorkspaceHeader | WorkspaceHeader.jsx | Enhanced — search palette, time context |
| ActivityBar | ActivityBar.jsx | Rewritten — severity encoding, delta summary |
| workspaceContext | workspaceContext.jsx | Enhanced — AI coordinator, search, selectedEntity |

## Components Refactored

### LayerRail.jsx
- Regrouped layers into: HAZARD, INFRASTRUCTURE, RESPONSE, INTELLIGENCE
- HAZARD: Flood
- INFRASTRUCTURE: Roads, Bridges, Buildings, Medical
- RESPONSE: Needs, Incidents, Operations, Offers
- INTELLIGENCE: Reports, Overrides, AI Alerts

### ContextPanel.jsx
- Removed two corrupted duplicate blocks (~300 lines of duplicated NeedDetail code)
- Fixed missing closing brace
- Wired AIAnalysisPanel to use context-cached analysis instead of independent fetch
- All existing dossier components preserved: NeedDetail, OperationDetail, OfferDetail, ReportDetail, FacilityDetail, SettlementDetail, RoadDetail, CreateNeedForm, CreateReportForm, CreateOfferForm

### ActivityBar.jsx
- Added severity encoding for all event types (critical/urgent/stable/information)
- Added delta summary bar showing: +X needs, -X resolved, +X reports, +X offers, X ops
- Preserved existing event click → map focus + panel open behavior

## New Components

None created as new files. All functionality was implemented by refactoring existing components.

## State Model

### workspaceContext.jsx additions

```javascript
// AI Coordinator
aiAnalysis: null,        // Cached analysis from /api/ai-coordinator/analysis
aiLoading: false,

// Selected entity (for map/panel sync)
selectedEntity: null,

// Search
searchQuery: "",
searchResults: [],
```

### New actions
- `SET_AI_ANALYSIS` — Store cached AI coordinator analysis
- `SET_AI_LOADING` — Track AI fetch state
- `SET_SELECTED_ENTITY` — Track currently selected map entity
- `SET_SEARCH_QUERY` / `SET_SEARCH_RESULTS` — Command search state

### New functions
- `fetchAiAnalysis()` — Fetch and cache AI coordinator analysis (called on initial load + 30s polling)
- `setSelectedEntity(entity)` — Set currently focused entity
- `performSearch(query)` — Client-side search across districts, settlements, needs, operations, roads, bridges

## Map/Panel Synchronization

The existing architecture already supports:
1. **Map click → Context panel**: MapCanvas `handleObjectClick` calls `openPanel(type, entityId, data)`
2. **Panel "View on Map"**: AI findings call `setMapCenter` to fly to location
3. **Activity click → Map + Panel**: ActivityBar calls `openPanel` which opens context panel

New additions:
- `selectedEntity` state in workspace context (available for future selection highlighting)
- Search results navigate via `setMapCenter` + `openPanel`

## AI Coordinator Integration

- Backend: `/api/ai-coordinator/analysis` (read-only, 3 detectors)
- Frontend: AIAnalysisPanel in ContextPanel reads from `state.aiAnalysis`
- Caching: Analysis is fetched on initial load and refreshed every 30 seconds
- Findings include `review_target` with `panel_type`, `entity_id`, `entity_data`, `map_center`, `district_id`
- Clicking "Review" on a finding centers the map and opens the relevant dossier

## Activity/Delta Integration

- ActivityBar shows delta summary: new needs, resolved needs, new reports, new offers, operation updates
- Each activity event has severity encoding:
  - `critical`: AI recommendation, coordination gap
  - `urgent`: need created, status changed
  - `stable`: need resolved, resource offered/accepted
  - `information`: operation updates, field updates
- Clicking an activity event opens the relevant entity in the context panel

## Search Integration

- Keyboard shortcut: `Cmd/Ctrl + K` opens command palette
- Searches across: districts, settlements, needs, operations, roads, bridges
- Results show entity type, name, and icon
- Selecting a result: centers map + opens context panel
- Arrow keys navigate results, Enter selects

## Responsive Behavior

- **Desktop**: Left rail (208px) | Map (flex) | Right panel (384px) | Bottom bar (40px)
- **Tablet**: LayerRail collapses to icon-only (40px), right panel becomes floating
- **Mobile**: Not yet implemented (later phase)

## Design Tokens

All components use the existing dark operational theme:
- Background: `#0f1419`
- Surface: `#1a2332`
- Border: `#2a3a4e`
- Text: `#c8d6e5` (primary), `#a0aec0` (secondary), `#6b7d93` (muted), `#4a5568` (subtle)
- Primary accent: `#4ea8de` (cyan)
- Critical: `#dc2626` (red)
- Urgent: `#d97706` (amber)
- Stable: `#16a34a` (green)
- Information: `#2563eb` (blue)
- AI: `#7c3aed` (purple)

## Tests

All existing tests pass:
- `test_ai_coordinator.py`: 147 passed
- `test_planner.py`: 31 passed
- `test_routing.py`: 31 passed
- `test_community_reports.py`: 14 passed
- `test_verification.py`: 17 passed
- `test_osm_pbf_ingestion.py`: 4 passed, 10 skipped (DB-dependent)
- **Total: 244+ passed, 0 failed**

## Files Changed

| File | Change Type | Lines Changed |
|------|-------------|---------------|
| frontend/src/lib/workspaceContext.jsx | Enhanced | +80 |
| frontend/src/components/workspace/WorkspaceHeader.jsx | Rewritten | 160 |
| frontend/src/components/workspace/LayerRail.jsx | Refactored | ~10 |
| frontend/src/components/workspace/ActivityBar.jsx | Rewritten | 140 |
| frontend/src/components/workspace/ContextPanel.jsx | Cleaned | -300 (removed duplicates) |
| docs/phase7b-operational-shell.md | New | — |

## Verification

```
Frontend build: ✅ (575KB JS, 48KB CSS)
Backend tests: ✅ (244+ passed)
DATABASE MODIFIED: NO
DATABASE DATA CHANGED: NO
DOCKER MODIFIED: NO
FLOOD DATA MODIFIED: NO
OSM DATA MODIFIED: NO
```

## What Was NOT Changed

- Database schema
- API endpoints
- Flood data
- OSM data
- Docker configuration
- Agent/planner architecture
- Backend business logic
- Map rendering engine
- Data models
