# RELIEFOS — PHASE 7B.1 DOCUMENTATION

## Operational Shell — Functional Completion

### Overview

Phase 7B.1 transforms the ReliefOS Operational Shell from a visual mockup into a fully functional
operational console where every control produces real changes in application state, data visibility,
map rendering, and panel content.

---

## Filter State Architecture

### Single Source of Truth

All filter state is managed centrally in `workspaceContext.jsx` via `useReducer`:

```javascript
filterState = {
  district: null | 'sivasagar' | 'jorhat' | 'charaideo' | 'golaghat',
  layers: {
    flood, floodHistory, roads, bridges, settlements, buildings,
    medical, organizations, needs, offers, operations, incidents,
    fieldReports, overrides, aiAlerts
  },
  urgency: null | 'critical' | 'high' | 'medium' | 'low',
  status: null | 'OPEN' | 'RESPONDING' | 'RESOLVED'
}
```

**No component maintains separate filter state.** All components consume from `useWorkspace()`.

### Filter → Data Flow

```
Filter Change (district/urgency/status)
    ↓
workspaceContext useEffect
    ↓
API calls with filter params
    ↓
State updated (SET_NEEDS, SET_ROADS, etc.)
    ↓
Components re-render with new data
    ↓
MapCanvas applies visibility/GeoJSON filters
    ↓
LayerRail shows updated counts
    ↓
ContextPanel shows scoped data
```

---

## District Scoping

### Districts

There are exactly four districts:

| District | ID | Flood Snapshot |
|----------|------|----------------|
| Sivasagar | sivasagar | flood_sivasagar_20260701 |
| Jorhat | jorhat | flood_jorhat_20260729 |
| Charaideo | charaideo | flood_charaideo_20260729 |
| Golaghat | golaghat | flood_golaghat_20260722 |

### ALL Districts View

When `district = null` (All Districts):

- **Flood layer**: Fetches all four districts' flood GeoJSON, merges into a single FeatureCollection
  with `district_id` in each feature's properties
- **Roads/Bridges/Medical**: Fetches from all districts
- **Settlements**: Shows all settlements
- **Needs/Operations/Offers**: Shows all (API returns all when no district_id filter)
- **AI Coordinator**: Analyzes full network context

### Single District View

When a district is selected (e.g., `jorhat`):

- **Flood layer**: Shows only Jorhat flood polygons
- **Roads/Bridges/Medical**: Fetched for Jorhat only
- **Settlements**: Filtered to Jorhat
- **Needs/Operations/Offers**: API-filtered by Jorhat
- **Field Reports**: Filtered by approximate geographic bounding box
- **AI Coordinator**: Scoped to Jorhat context

### UI Controls

District selection is available in two places:

1. **WorkspaceHeader** — dropdown selector in the top bar
2. **LayerRail** — district selector at top of layer groups

Both controls use `setFilter('district', value)` which triggers data refetching.

---

## Flood Layer

### Current Flood State (Layer: "Flood")

- **ALL Districts**: Merged FeatureCollection from all four districts
  - Each feature carries `district_id` in properties
  - Color-coded by district for visual distinction
- **Single District**: District-specific flood GeoJSON
- Data source: `/api/districts/{id}/flood-geojson`

### Flood History (Layer: "Flood History")

- Toggle: `layers.floodHistory`
- When enabled: Shows snapshot selector in LayerRail
- Snapshots fetched from `/api/flood-snapshots`
- Selecting a snapshot loads its GeoJSON from `/api/flood-snapshots/{id}/geojson`
- Default: Active flood layer (latest) is shown; history is separate

---

## Infrastructure Layers

### Roads

- **Toggle**: `layers.roads` (ON by default)
- **Data**: Fetched per-district via `/api/districts/{id}/roads`
- **Rendering**: GeoJSON LineString features with status-based coloring
  - Open: green (`#16a34a`)
  - Blocked: red dashed (`#dc2626`)
  - Uncertain: amber (`#d97706`)
- **Click**: Opens `road` context panel with detail + override option

### Bridges

- **Toggle**: `layers.bridges` (ON by default)
- **Data**: Roads where `is_bridge=true` or `tags.bridge=yes`
- **Rendering**: Same GeoJSON layer as roads, thicker lines
- **Click**: Opens bridge detail in context panel
- **Override display**: Shows base state + current operational state

### Settlements

- **Toggle**: `layers.settlements` (ON by default)
- **Data**: Fetched per-district via `/api/districts/{id}/settlements`
- **Rendering**: Circle markers at lat/lon
- **District filter**: Applied client-side
- **Click**: Opens settlement dossier

### Buildings

- **Toggle**: `layers.buildings` (OFF by default)
- **Data**: Viewport-bounded via `/api/districts/{id}/buildings?west=&south=&east=&north=&zoom=`
- **Performance**: Only loads at zoom >= 13
- **Limit**: Maximum 2,000 markers rendered as DOM elements
- **District**: Uses selected district; for ALL, defaults to first district
- **Click**: Opens building detail panel

### Medical

- **Toggle**: `layers.medical` (ON by default)
- **Data**: Fetched per-district via `/api/districts/{id}/medical-facilities`
- **Rendering**: Circle markers with H+ icon
- **Override awareness**: Orange marker if facility has active override
- **Click**: Opens facility detail + override action

---

## Response Layers

### Organizations

- **Toggle**: `layers.organizations` (OFF by default)
- **Data**: Public organization data from `/api/organizations`
- **Rendering**: Blue circle markers at district center
- **Privacy**: Only public data exposed; no private NGO state
- **Click**: Opens organization dossier with capabilities, contact, status

### Needs

- **Toggle**: `layers.needs` (ON by default)
- **Data**: Filtered by district, urgency, status via API params
- **Rendering**: Circle markers sized by urgency
  - Critical: Large red (28px)
  - High: Medium amber (24px)
  - Medium/Low: Small (20px)
- **Click**: Opens full Need dossier with coordination actions
- **Filters affected**: district, urgency, status all filter needs on map

### Operations

- **Toggle**: `layers.operations` (ON by default)
- **Data**: Filtered by district via API; status filter maps UI→backend values
- **Rendering**: Diamond markers colored by status
- **Click**: Opens operation detail with status management

### Offers

- **Toggle**: `layers.offers` (OFF by default)
- **Data**: Filtered by district via API
- **Rendering**: Triangle markers
- **Click**: Opens offer detail with matching needs

---

## Intelligence Layers

### Field Reports

- **Toggle**: `layers.fieldReports` (ON by default)
- **Data**: All reports from `/api/field-intelligence/history`
- **District filter**: Approximate geographic bounding box from district settlements
- **Rendering**: Square markers; green if verified, indigo if unverified
- **Click**: Opens report dossier with source, timestamp, verification state

### Overrides

- **Toggle**: `layers.overrides` (ON by default)
- **Data**: Active overrides from `/api/overrides`
- **Rendering**: Overrides applied to roads/bridges/medical via status coloring
- **Click**: Shows override dossier via the affected entity's panel

### AI Alerts

- **Toggle**: `layers.aiAlerts` (OFF by default)
- **Behavior**: When enabled, opens the AI Coordinator panel
- **Data**: Analysis from `/api/ai-coordinator/analysis`
- **Findings**: Clickable — focuses map target and opens context panel

---

## Severity Filters

### UI Controls

Four urgency buttons: CRITICAL, HIGH, MEDIUM, LOW

- **Behavior**: Toggle-based (click to select, click again to deselect)
- **State**: `filters.urgency` in workspaceContext
- **Data flow**:
  - MapCanvas: `visibleNeeds` filtered by urgency
  - LayerRail counts: Not urgency-filtered (show total for district)
  - API: Urgency passed as query param to `/api/needs`

### Filter Effect

| Filter | Map Markers | Lists | AI Context |
|--------|-------------|-------|------------|
| CRITICAL | Only critical needs | Scoped | Scoped |
| HIGH | Only high needs | Scoped | Scoped |
| MEDIUM | Only medium needs | Scoped | Scoped |
| LOW | Only low needs | Scoped | Scoped |

---

## Status Filters

### UI Controls

Three status buttons: OPEN, RESPONDING, RESOLVED

- **Behavior**: Toggle-based
- **State**: `filters.status` in workspaceContext
- **Mapping**: UI values map to backend status enums
  - OPEN → OPEN (needs) / PLANNING (operations)
  - RESPONDING → RESPONDING (needs) / ACTIVE (operations)
  - RESOLVED → RESOLVED (needs) / COMPLETED (operations)

### Data Flow

- **Needs**: Filtered via API query param
- **Operations**: Filtered client-side using status mapping
- **Map**: Markers filtered
- **Activity bar**: Shows filtered counts
- **AI coordinator**: Scoped to filtered data

---

## Search Behavior

### Context-Aware Search

The search function (`performSearch` in workspaceContext) searches across loaded state data:

- When ALL districts: searches all loaded data
- When district selected: data is already district-scoped from API fetches
- Results include: districts, settlements, needs, operations, roads, bridges, medical facilities, organizations

### Search → Map Interaction

1. User types query → `performSearch(query)`
2. Results filtered from in-memory state
3. User selects result → `setMapCenter([lat, lon])` + `openPanel(type, id, data)`
4. Map flies to location
5. ContextPanel opens with entity dossier

---

## AI Alert Behavior

### Toggle Behavior

- Clicking "AI Alerts" in LayerRail:
  1. Enables the `aiAlerts` layer
  2. Opens the AI Coordinator panel (`openPanel('aiAnalysis')`)
- The AI Coordinator panel fetches from `/api/ai-coordinator/analysis`
- Findings with `review_target` are clickable
- Click on finding:
  1. Map centers on target location
  2. Entity panel opens with target data

---

## Layer State Management

Every layer has:

| Property | Description |
|----------|-------------|
| `enabled` | `state.layers[layerId]` — boolean toggle |
| `loading` | `state.loading[layerKey]` — loading indicator |
| `data` | `state[layerDataKey]` — the loaded data array |
| `count` | Computed from data length (respecting district filter) |

### State Synchronization

- Toggle in LayerRail → `toggleLayer(id)` → reducer flips boolean
- Filter change in WorkspaceHeader → `setFilter(key, value)` → useEffect triggers refetch
- Data arrives → `SET_*` action → loading clears → components re-render

---

## Performance Strategy

### Buildings

- Only loaded at zoom >= 13
- Viewport-bounded API requests (bbox params)
- Maximum 2,000 DOM markers
- District-scoped by default

### Roads/Bridges/Medical

- Fetched per-district (not globally)
- GeoJSON rendered via Leaflet layer (GPU-accelerated)
- Visibility toggled via React conditional rendering

### Flood Data

- Merged FeatureCollection for ALL view
- Single district request for filtered view
- Polygon features (not individual markers)

### General

- `useMemo` for derived/filtered data
- `useCallback` for stable function references
- Lazy panel hydration (panels only mount when opened)
- 30-second polling for operational data (needs, operations, activity)

---

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `frontend/src/lib/workspaceContext.jsx` | Modified | Multi-district flood aggregation, buildings district handling |
| `frontend/src/components/workspace/MapCanvas.jsx` | Modified | Flood color per district, field report district filter, operations status filter, data status bar |
| `frontend/src/components/workspace/LayerRail.jsx` | Modified | District-filtered counts, AI Alerts → open panel, useCallback import |
| `docs/phase7b1-functional-shell.md` | Created | This documentation |

---

## Test Data Rule

- No synthetic data created
- All data comes from existing backend APIs
- Empty states shown when no data exists
- Development DB unchanged

---

## Acceptance Criteria Verification

| Criterion | Status |
|-----------|--------|
| ALL DISTRICTS loads four flood contexts | ✅ |
| District filter scopes entire operational UI | ✅ |
| Flood layer shows all four districts by default | ✅ |
| Roads toggle functional | ✅ |
| Bridges toggle functional | ✅ |
| Buildings viewport-bounded at zoom >= 13 | ✅ |
| Medical toggle functional | ✅ |
| Settlements toggle functional | ✅ |
| Organizations toggle functional | ✅ |
| Needs toggle functional | ✅ |
| Reports toggle functional | ✅ |
| Overrides integrated | ✅ |
| AI Alerts opens AI panel | ✅ |
| Severity filters affect data visibility | ✅ |
| Status filters affect data visibility | ✅ |
| Search respects district context | ✅ |
| Map selection opens ContextPanel | ✅ |
| No private org state leaked | ✅ |
| No synthetic data added | ✅ |
| No database modified | ✅ |

---

## DATABASE MODIFIED: NO
## DATABASE DATA CHANGED: NO
## DOCKER MODIFIED: NO
## REAL FLOOD DATA MODIFIED: NO
## OSM DATA MODIFIED: NO
## SYNTHETIC DATA ADDED: NO
