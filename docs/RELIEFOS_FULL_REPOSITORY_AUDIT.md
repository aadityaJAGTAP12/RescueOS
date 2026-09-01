# RELIEFOS — FULL REPOSITORY ARCHITECTURE AUDIT

## Pre-Implementation Audit for the Final Unified Console

**Date:** 2026-09-01
**Status:** AUDIT ONLY — No code changes made

---

## 1. EXECUTIVE SUMMARY

ReliefOS is a **map-first disaster-response coordination platform** built on Flask (backend) + React/Leaflet (frontend) with PostgreSQL/PostGIS for spatial data. The codebase is well-structured with clean separation between data models, repository pattern, tools, agents, API, and frontend.

### What genuinely exists:
- **Data layer:** Complete SQLAlchemy/PostGIS schema with 14 tables (districts, settlements, flood_snapshots, field_reports, overrides, buildings, medical_facilities, roads, organizations, needs, resource_offers, operations, operation_participants, activity_events, notifications)
- **Repository pattern:** InMemoryRepository (tests) + PostgresRepository (production) with full CRUD for all Phase 7B entities
- **Collaboration engine:** Need → Resource Offer → Match → Confirm → Operation lifecycle is **fully implemented** end-to-end (backend + frontend)
- **AI coordinator:** Read-only operational analysis detecting coordination gaps, duplicate responses, and consequence alerts
- **Map-first workspace:** Full Leaflet map with flood, roads, bridges, settlements, needs, operations, offers, field reports, and overrides layers
- **Context panel:** Complete dossier panels for needs, operations, offers, reports, facilities with inline actions
- **Planning engine:** Deterministic, district-agnostic planner with cross-district queries, temporal flood queries, resource allocation
- **OSRM routing:** Real driving routes with haversine fallback
- **Field intelligence:** Community reports + KoboToolbox webhook + free-text extraction via LLM
- **Overrides:** Manual coordinator overrides with system_status vs override_status tracking

### What is only conceptual:
- NGO Main Agent (private workspace)
- NGO private/public state boundary
- Specialist worker agents (exist as Strands agents but not wired into the Network Main Agent architecture)
- Temporal UI controls (time slider)
- Command palette / search (UI shell exists, search not functional)
- Semantic deduplication of field reports
- Proactive AI alerts
- Network mode vs org mode toggle
- Responsive tablet/mobile layouts

### What the largest frontend gap is:
The **ContextPanel** has duplicate code blocks (the file is ~2000 lines with repeated NeedDetail sections). The panel handles create forms (need, report, offer) but there is **no Organization detail panel**, **no AI analysis panel** (referenced but not fully implemented), and the **search/command palette** is non-functional.

### What the largest backend/agent gap is:
The **NGO workspace** is completely missing. Organizations are flat records with no private state, no resource inventory, no teams, no missions, no publication mechanism. The specialist worker agents exist but are not orchestrated by a Network Main Agent — they're individually callable via Strands.

### What the minimum next implementation step is:
Wire the AI Coordinator findings to the frontend ActivityBar and ContextPanel. The backend endpoint `/api/ai-coordinator/analysis` exists and returns structured findings, but the frontend never calls it.

### What NOT to rebuild:
- Data models (all Phase 7B entities are correctly modeled)
- Repository pattern (both implementations are solid)
- Matching engine (deterministic, well-tested)
- Activity events (append-only, working)
- Override system (working, tested)
- Planning engine (cross-district, temporal, resource-aware)
- Map layers and context panel (fully functional)

---

## 2. REPOSITORY TREE

```
reliefos/
├── CLAUDE.md                          # Architecture blueprint (frozen)
├── README.md
├── RUNNING_THE_SYSTEM.md
├── requirements.txt                   # Python dependencies
├── docker-compose.yml                 # PostGIS 16-3.4
├── kobo_webhook_receiver.py           # KoboToolbox webhook → submit_report()
├── test_kobo_webhook_locally.py       # Local webhook test
│
├── agent/                             # Backend (Flask + Python)
│   ├── __init__.py
│   ├── main.py                        # CLI entry point (ranking + assessment demo)
│   ├── api.py                         # Flask API — ALL endpoints (~1600 lines)
│   ├── config.py                      # Model config + KNOWN_LOCATIONS + Overpass config
│   ├── assessment.py                  # run_relief_assessment() — main entry point
│   ├── planner.py                     # PlannerOrchestrator — query orchestration
│   ├── matching.py                    # Deterministic Need↔Offer matching engine
│   ├── overrides.py                   # Manual status overrides (JSON file storage)
│   ├── community_reports.py           # Community/field report storage (JSON file)
│   ├── verification.py                # LLM extraction guardrails
│   ├── data_loader.py                 # Flood data loading + cache helpers
│   │
│   ├── data/                          # Data layer
│   │   ├── models.py                  # All domain models (16 dataclasses)
│   │   ├── repository.py              # Abstract DataRepository + InMemoryRepository
│   │   ├── postgres_repository.py     # PostgresRepository (PostGIS)
│   │   ├── schema.py                  # SQLAlchemy schema (14 tables)
│   │   └── migration.py               # Data migration (GeoJSON → PostGIS)
│   │
│   ├── agents/                        # Strands LLM agents
│   │   ├── coordinator_agent.py       # LLM synthesis + multi-agent orchestration
│   │   ├── flood_assessment_agent.py  # Flood + exposure sub-agent
│   │   ├── accessibility_agent.py     # Medical + road accessibility sub-agent
│   │   ├── allocation_agent.py        # PDC scoring sub-agent
│   │   └── supply_matching_agent.py   # Community report → supply matching
│   │
│   ├── tools/                         # Deterministic tools
│   │   ├── flood_tool.py              # Flood status check
│   │   ├── exposure_tool.py           # Building exposure analysis
│   │   ├── accessibility_tool.py      # Medical facility accessibility
│   │   ├── allocation_tool.py         # PDC scoring + resource allocation
│   │   ├── routing_tool.py            # OSRM routing + haversine fallback
│   │   ├── road_status_tool.py        # Road status with overrides
│   │   ├── field_intelligence_tool.py # Free-text → structured extraction
│   │   ├── query_parser_tool.py       # LLM query parsing + location resolution
│   │   └── region_scan_tool.py        # Grid-based region flood scan
│   │
│   └── gee/                           # Google Earth Engine pipeline
│       ├── config.py
│       ├── discover_s1.py             # Sentinel-1 scene discovery
│       ├── flood_pipeline.py          # GEE flood mapping pipeline
│       ├── export.py / export_district.py
│       ├── validation.py
│       └── runs/                      # Pipeline run outputs
│
├── frontend/                          # React + Vite + Leaflet
│   ├── package.json                   # React 19, Leaflet, Recharts, Tailwind 4
│   ├── vite.config.js                 # Dev proxy to Flask :5001
│   ├── index.html
│   │
│   └── src/
│       ├── main.jsx                   # Entry point
│       ├── App.jsx                    # Router: / → NetworkWorkspace, /legacy → Dashboard
│       ├── index.css                  # Design tokens + Tailwind theme
│       │
│       ├── components/
│       │   ├── workspace/             # NEW map-first workspace
│       │   │   ├── NetworkWorkspace.jsx   # Shell: header + layer rail + map + panel + activity
│       │   │   ├── WorkspaceHeader.jsx    # Top bar: logo, district selector, AI, notifications, search
│       │   │   ├── LayerRail.jsx          # Left rail: layer toggles + district filter + actions
│       │   │   ├── MapCanvas.jsx          # Center: Leaflet map with all layers
│       │   │   ├── ContextPanel.jsx       # Right panel: dossiers + forms (~2000 lines)
│       │   │   └── ActivityBar.jsx        # Bottom bar: critical needs + activity stream
│       │   │
│       │   ├── Header.jsx             # Legacy header
│       │   ├── LocationSelector.jsx   # Legacy location dropdown
│       │   ├── SituationMap.jsx       # Legacy map component
│       │   ├── QueryInput.jsx         # Free-text query input
│       │   ├── OperationalAnswer.jsx  # Operational answer display
│       │   ├── EvidencePanel.jsx      # Evidence cards
│       │   ├── DataGapsPanel.jsx      # Data gaps display
│       │   ├── StagedReveal.jsx       # Agent trace timeline
│       │   └── FieldIntelligencePage.jsx  # Legacy field intelligence page
│       │
│       └── lib/
│           ├── workspaceContext.jsx   # Global state (useReducer + Context)
│           ├── utils.js               # cn(), formatValue(), getCategoryStyle()
│           └── mapStyles.js           # MAP_STYLES constants (road/bridge/route)
│
├── data/                              # Data assets
│   ├── sivasagar_flood.geojson        # Flood polygons (Sentinel-1 SAR)
│   ├── districts_gee.geojson          # District boundaries
│   ├── charaideo_gee.geojson
│   ├── golaghat_gee.geojson
│   ├── community_reports.json         # Field/community reports (JSON storage)
│   ├── overrides.json                 # Manual overrides (JSON storage)
│   ├── cache/                         # Overpass API response cache
│   └── raw/                           # Raw data files
│
├── scripts/
│   ├── db_init.py                     # Database initialization
│   └── ingest/                        # Data ingestion scripts
│       ├── base.py
│       ├── all.py
│       ├── boundaries.py / buildings.py / flood.py / medical.py
│       ├── roads.py / settlements.py / validate.py
│       └── osm_pbf.py                 # OSM PBF ingestion
│
├── osrm/                              # OSRM routing server
│   ├── docker-compose.yml
│   ├── setup.sh
│   └── README.md
│
├── tests/                             # Test suite
│   ├── conftest.py                    # Shared fixtures
│   ├── test_planner.py                # Planner integration tests
│   ├── test_ai_coordinator.py         # AI coordinator unit tests
│   ├── test_phase7b.py                # Collaboration lifecycle tests
│   ├── test_phase7d.py                # Needs/offers/operations tests
│   ├── test_allocation.py             # PDC scoring + allocation tests
│   ├── test_assessment.py             # Assessment tests
│   ├── test_routing.py                # OSRM routing tests
│   ├── test_override_routing.py       # Override-aware routing tests
│   ├── test_flood_tool.py / test_flood_pipeline.py
│   ├── test_community_reports.py / test_verification.py
│   ├── test_osm_pbf_ingestion.py / test_export_district.py
│   ├── test_priority.py / test_step1_multidistrict.py
│   ├── test_phase3.py / test_phase4.py
│   ├── test_postgres_repository.py / test_agent_trace.py
│   └── __init__.py
│
└── docs/
    ├── phase7-collaborative-workspace.md
    ├── phase7b-map-first-workspace.md
    └── RELIEFOS_FULL_REPOSITORY_AUDIT.md  # This document
```

---

## 3. FRONTEND ARCHITECTURE

### Framework & Tooling
- **React 19** with Vite 8
- **Tailwind CSS 4** (via `@tailwindcss/vite`)
- **Leaflet + react-leaflet** (NOT MapLibre/deck.gl)
- **Recharts** (available, not currently used in workspace)
- **date-fns** for time formatting
- **lucide-react** for icons
- **react-router-dom v7** for routing
- **class-variance-authority + clsx + tailwind-merge** for utility classes

### Routing
- `/` → `NetworkWorkspace` (primary map-first console)
- `/legacy` → `DashboardPage` (original assessment dashboard)
- `/field-intelligence` → `FieldIntelligencePage`

### State Management
**`workspaceContext.jsx`** — Global state via `useReducer` + React Context:

| State Key | Type | Purpose |
|-----------|------|---------|
| `mapCenter` | `[lat, lon]` | Map viewport center |
| `mapZoom` | `number` | Map zoom level |
| `layers` | `object` | Layer visibility toggles (13 layers) |
| `filters` | `object` | District, urgency, status filters |
| `panelOpen/Type/EntityId/Data` | mixed | Right context panel state |
| `floodData` | `GeoJSON` | Flood polygons |
| `districts` | `array` | District list |
| `settlements` | `array` | Settlement markers |
| `roads` | `array` | Road features |
| `bridges` | `array` | Bridge features |
| `needs` | `array` | Shared needs |
| `offers` | `array` | Resource offers |
| `operations` | `array` | Operations |
| `fieldReports` | `array` | Field/community reports |
| `overrides` | `object` | Active overrides (keyed by target_id) |
| `activity` | `array` | Activity events |
| `notifications` | `array` | Notifications |
| `loading` | `object` | Per-entity loading states |

Data is fetched on mount and polled every 30 seconds (needs, offers, operations, activity, notifications).

### Component Inventory

| File | Component | Purpose | Reusable? | Redesign Needed? |
|------|-----------|---------|-----------|-----------------|
| `NetworkWorkspace.jsx` | `NetworkWorkspace` | Shell layout | Yes | Minor |
| `WorkspaceHeader.jsx` | `WorkspaceHeader` | Top bar | Yes | Search non-functional |
| `LayerRail.jsx` | `LayerRail` | Left layer toggles | Yes | No |
| `MapCanvas.jsx` | `MapCanvas` | Leaflet map + all layers | Yes | No (but needs MapLibre migration per spec) |
| `ContextPanel.jsx` | `ContextPanel` | Right dossier panel | Needs refactor | **Yes** — duplicate code blocks, missing AI panel |
| `ActivityBar.jsx` | `ActivityBar` | Bottom activity stream | Yes | Needs delta summary |
| `index.css` | Design tokens | Console dark theme | Yes | Partially matches spec |

---

## 4. MAP ARCHITECTURE

### Current Implementation
- **Library:** Leaflet (via react-leaflet 5.0)
- **Tile layer:** CartoDB dark_all basemap
- **NOT MapLibre/deck.gl** as specified in CLAUDE.md — this is the primary deviation

### Layer Table

| Layer | Exists | Data Source | Renderer | Toggleable? | Selectable? | Redesign? |
|-------|--------|-------------|----------|-------------|-------------|-----------|
| Flood | ✅ | GeoJSON (static file or PostGIS) | GeoJSON polygons | ✅ | ✅ popup | No |
| Roads | ✅ | PostGIS roads table | GeoJSON LineString | ✅ | ✅ popup + panel | No |
| Bridges | ✅ | Filtered roads (is_bridge=True) | Same as roads | ✅ | ✅ | No |
| Settlements | ✅ | PostGIS settlements | Circle markers | ✅ | ✅ popup | No |
| Buildings | ✅ (toggle exists) | PostGIS buildings | (Not rendered — no data in current districts) | ✅ | — | Needs data |
| Medical | ✅ | PostGIS medical_facilities | Custom SVG icon markers | ✅ | ✅ popup + panel | No |
| Needs | ✅ | API /api/needs | Circle markers (urgency-colored) | ✅ | ✅ panel | No |
| Operations | ✅ | API /api/operations | Diamond markers (status-colored) | ✅ | ✅ panel | No |
| Offers | ✅ | API /api/offers | Triangle markers | ✅ | ✅ panel | No |
| Incidents | ✅ (toggle exists) | — | No renderer yet | ✅ | — | Missing |
| Field Reports | ✅ | API /api/field-intelligence/history | Square markers | ✅ | ✅ panel | No |
| Overrides | ✅ | API /api/overrides | Applied to road/facility styling | ✅ | Via parent | No |
| AI Alerts | ✅ (toggle exists) | — | No renderer yet | ✅ | — | Missing |

### Map → Panel Synchronization
- ✅ Click map object → `openPanel(type, entityId, data)` → ContextPanel renders dossier
- ✅ Right-click map → `openPanel('createReport', null, {lat, lon})` → CreateReportForm

### Panel → Map Synchronization
- ✅ `setMapCenter` dispatch available but not wired from ContextPanel actions
- ❌ No "fly to" when opening a panel from ActivityBar

### Performance
- No clustering for large feature sets
- No viewport-aware loading (fetches all data for district)
- GeoJSON rendered via react-leaflet `<GeoJSON>` — may struggle with thousands of features
- Markers rendered individually (not virtualized)

---

## 5. BACKEND / API AUDIT

### Endpoint Inventory

#### Situation / Geography
| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| GET | `/api/locations` | List known locations | ✅ Implemented |
| GET | `/api/districts` | List all districts | ✅ Implemented |
| GET | `/api/districts/:id/flood-geojson` | Flood GeoJSON per district | ✅ Implemented |
| GET | `/api/districts/:id/settlements` | Settlements per district | ✅ Implemented |
| GET | `/api/districts/:id/roads` | Roads per district (JSON) | ✅ Implemented |
| GET | `/api/districts/:id/roads/geojson` | Roads per district (GeoJSON) | ✅ Implemented |
| GET | `/api/districts/:id/bridges` | Bridges per district | ✅ Implemented |
| GET | `/api/flood-geojson` | Legacy flood GeoJSON | ✅ Implemented |

#### Assessment / Query
| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| GET | `/api/assess` | Full assessment for location | ✅ Implemented |
| POST | `/api/query` | Free-text query → structured response | ✅ Implemented |
| POST | `/api/planner` | Planner orchestrator | ✅ Implemented |

#### Needs
| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| GET | `/api/needs` | List needs (filterable) | ✅ Implemented |
| POST | `/api/needs` | Create need | ✅ Implemented |
| GET | `/api/needs/:id` | Get need | ✅ Implemented |
| PATCH | `/api/needs/:id` | Update need | ✅ Implemented |
| GET | `/api/needs/:id/matches` | Find matching offers | ✅ Implemented |

#### Resource Offers
| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| GET | `/api/offers` | List offers (filterable) | ✅ Implemented |
| POST | `/api/offers` | Create offer | ✅ Implemented |
| PATCH | `/api/offers/:id` | Update offer | ✅ Implemented |

#### Matching / Collaboration
| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| POST | `/api/matches/:need_id/:offer_id/confirm` | Confirm match → create Operation | ✅ Implemented |

#### Operations
| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| GET | `/api/operations` | List operations (filterable) | ✅ Implemented |
| POST | `/api/operations` | Create operation | ✅ Implemented |
| GET | `/api/operations/:id` | Get operation + participants | ✅ Implemented |
| PATCH | `/api/operations/:id` | Update operation | ✅ Implemented |

#### Organizations
| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| GET | `/api/organizations` | List organizations | ✅ Implemented |
| POST | `/api/organizations` | Create organization | ✅ Implemented |
| GET | `/api/organizations/:id` | Get organization | ✅ Implemented |

#### Activity / Notifications
| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| GET | `/api/activity` | List activity events | ✅ Implemented |
| GET | `/api/notifications` | List notifications | ✅ Implemented |
| POST | `/api/notifications/:id/read` | Mark notification read | ✅ Implemented |

#### Routing
| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| GET | `/api/route` | Single route (OSRM) | ✅ Implemented |
| POST | `/api/routes` | Multiple routes | ✅ Implemented |
| POST | `/api/recommend-destination` | Route-aware destination recommendation | ✅ Implemented |

#### Field Intelligence
| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| POST | `/api/field-intelligence` | Submit raw text → LLM extraction → store | ✅ Implemented |
| GET | `/api/field-intelligence/history` | List field intelligence reports | ✅ Implemented |

#### Overrides
| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| POST | `/api/override` | Apply override | ✅ Implemented |
| GET | `/api/override/status` | Get operational status | ✅ Implemented |
| GET | `/api/overrides` | List all overrides | ✅ Implemented |

#### AI Coordinator
| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| GET | `/api/ai-coordinator/analysis` | Read-only analysis findings | ✅ Implemented |

---

## 6. DATABASE / MODEL AUDIT

### Schema Tables (PostgreSQL + PostGIS)

| Table | Purpose | Key Fields | Ownership | Status |
|-------|---------|------------|-----------|--------|
| `districts` | Administrative boundaries | id, name, geometry(Polygon) | SHARED | ✅ In use |
| `settlements` | Known locations | id, name, district_id, lat/lon, location(Point) | SHARED | ✅ In use |
| `flood_snapshots` | Temporal flood observations | id, district_id, observed_at, geometry(MultiPolygon), provenance | SHARED | ✅ In use |
| `field_reports` | Community/field intelligence | id, district_id, lat/lon, source_type, raw_text, verification_state | SHARED | ✅ In use |
| `overrides` | Manual status overrides | id, target_type, target_id, override_status, active | SHARED | ✅ In use |
| `buildings` | OSM building data | id, district_id, lat/lon, tags, in_flood_zone | SHARED | ✅ Schema exists |
| `medical_facilities` | OSM medical facilities | id, district_id, name, lat/lon, facility_type | SHARED | ✅ In use |
| `roads` | OSM road data | id, district_id, name, geometry(MultiLineString), is_bridge | SHARED | ✅ In use |
| `organizations` | Relief organizations | id, name, organization_type, published_capabilities | SHARED | ✅ In use |
| `needs` | Shared resource needs | id, need_type, title, urgency, status, lat/lon | SHARED | ✅ In use |
| `resource_offers` | Published resource offers | id, organization_id, resource_type, quantity, status | SHARED | ✅ In use |
| `operations` | Coordinated response actions | id, name, need_id, lead_organization_id, status | SHARED | ✅ In use |
| `operation_participants` | Operation membership | operation_id, organization_id, role | SHARED | ✅ In use |
| `activity_events` | Append-only activity log | id, entity_type, entity_id, event_type, detail | SHARED | ✅ In use |
| `notifications` | User notifications | id, recipient_id, notification_type, read | MIXED | ✅ Schema exists |

### Domain Models (agent/data/models.py)

All 16 dataclasses are implemented with `to_dict()` serialization:
- `Provenance` enum: REAL, DERIVED, SYNTHETIC, MANUAL_OVERRIDE
- `VerificationState` enum: UNVERIFIED, VERIFIED, DISPUTED
- `District`, `Settlement`, `FloodSnapshot`, `Building`, `MedicalFacility`, `Road`
- `FieldReport`, `Override`
- `Organization`, `Need`, `ResourceOffer`, `Operation`, `ActivityEvent`, `Notification`
- `QueryRequest` (internal planning contract)

### Repository Pattern

| Implementation | Location | Purpose | Status |
|---------------|----------|---------|--------|
| `DataRepository` | `agent/data/repository.py` | Abstract interface | ✅ Complete |
| `InMemoryRepository` | `agent/data/repository.py` | Dict-backed (tests) | ✅ Complete |
| `PostgresRepository` | `agent/data/postgres_repository.py` | PostgreSQL + PostGIS | ✅ Complete |

The `get_repository()` factory selects based on `DATABASE_URL` env var or `RELIEFOS_MEMORY=1`.

---

## 7. COLLABORATION / GITHUB-LIKE ENGINE AUDIT

### Lifecycle Trace

| Step | Backend | Frontend | Database | API Endpoint | Status |
|------|---------|----------|----------|-------------|--------|
| **Need Created** | `api_create_need()` | `CreateNeedForm` in ContextPanel | `needs` table + `activity_events` | POST `/api/needs` | ✅ Working |
| **Resource Offer** | `api_create_offer()` | `CreateOfferForm` in ContextPanel | `resource_offers` + `activity_events` | POST `/api/offers` | ✅ Working |
| **Match Found** | `find_matches_for_need()` | `handleFindResources()` in NeedDetail | Read-only (queries offers) | GET `/api/needs/:id/matches` | ✅ Working |
| **Match Confirmed** | `api_confirm_match()` | `handleConfirmMatch()` in NeedDetail | Creates `operations` + `activity_events` + updates offer/need status | POST `/api/matches/:need/:offer/confirm` | ✅ Working |
| **Operation Active** | `api_update_operation()` | `handleStatusChange()` in OperationDetail | Updates `operations` + `activity_events` | PATCH `/api/operations/:id` | ✅ Working |
| **Need Resolved** | `api_update_need()` | `handleStatusChange()` in NeedDetail | Updates `needs` + `activity_events` | PATCH `/api/needs/:id` | ✅ Working |
| **Activity Logged** | `append_activity_event()` | `ActivityBar` reads events | `activity_events` (append-only) | GET `/api/activity` | ✅ Working |

### What exists only in backend:
- Matching algorithm (`matching.py`) — fully implemented with scoring, compatibility, reasons
- Match confirmation creates Operation with metadata (offer_id, quantity_committed)

### What exists in frontend:
- Complete Need dossier with status changes, resource matching, activity history
- Operation dossier with status changes, participants
- Create forms for needs, offers, reports
- Activity bar with event stream

### What is connected end-to-end:
- **The full lifecycle works:** Create Need → Create Offer → Find Matches → Confirm → Operation → Update → Resolve

---

## 8. AI / AGENT AUDIT

### Agent Inventory

| Agent | Exists | Actually Invoked? | Tools | Role | Status |
|-------|--------|-------------------|-------|------|--------|
| **Coordinator Agent** | `agent/agents/coordinator_agent.py` | Yes (when `use_llm=True`) | flood_assessment_agent_tool, accessibility_agent_tool, supply_matching_agent_tool | LLM synthesis of evidence | ✅ IMPLEMENTED |
| **Flood Assessment Agent** | `agent/agents/flood_assessment_agent.py` | Yes (via coordinator) | get_flood_status, get_building_exposure, scan_region | Flood risk assessment | ✅ IMPLEMENTED |
| **Accessibility Agent** | `agent/agents/accessibility_agent.py` | Yes (via coordinator) | get_medical_accessibility, get_road_status | Medical + road accessibility | ✅ IMPLEMENTED |
| **Allocation Agent** | `agent/agents/allocation_agent.py` | Yes (via coordinator) | calculate_priority | PDC scoring | ✅ IMPLEMENTED |
| **Supply Matching Agent** | `agent/agents/supply_matching_agent.py` | Yes (via coordinator) | get_reports_near_tool, match_supplies | Community report → supply matching | ✅ IMPLEMENTED |
| **AI Coordinator (Network)** | `agent/ai_coordinator.py` | Yes (via API endpoint) | None (reads repository directly) | Read-only operational analysis | ✅ IMPLEMENTED |
| **Network Main Agent** | — | No | — | Orchestrate specialist workers | ❌ MISSING |
| **NGO Main Agent** | — | No | — | Private workspace intelligence | ❌ MISSING |
| **NGO Workers** | — | No | — | Inventory, logistics, team, mission, field | ❌ MISSING |
| **Network Specialist Workers** | — | Partial | — | Situation, exposure, medical, logistics, access, field, coordination, evidence | ❌ CONCEPTUAL |

### Planner Architecture

`agent/planner.py` — `PlannerOrchestrator`:

```
User Query → parse_operational_query() → PlannerOrchestrator.plan()
    → _build_planning_request()
    → _select_capabilities()
    → _resolve_locations()
    → _execute_tools()
    → _rank_locations()
    → _allocate_resources()
    → _synthesize()
    → PlanningResult
```

The planner is **district-agnostic** and uses repository-backed location resolution. It supports cross-district queries, temporal flood queries, resource constraints, and uncertainty reporting.

### AI Coordinator Analysis

`agent/ai_coordinator.py` — `run_coordinator_analysis()`:

Three detectors:
1. **Coordination Gap:** OPEN needs older than threshold with no responders
2. **Duplicate Response:** Multiple operations/offers on same need
3. **Consequence Alert:** Blocked road overrides affecting active operations

Each finding includes `review_target` (panel_type, entity_id, entity_data, map_center, district_id) for frontend navigation.

---

## 9. NGO WORKSPACE AUDIT

### Status: LARGELY MISSING

| Component | Status | Notes |
|-----------|--------|-------|
| Organization model | ✅ EXISTS | `Organization` dataclass + DB table |
| Organization CRUD API | ✅ EXISTS | GET/POST/GET/:id |
| Organization users | ❌ MISSING | No user/org relationship |
| Resource inventory | ❌ MISSING | No private resource tracking |
| Teams | ❌ MISSING | No team model |
| Missions | ❌ MISSING | No mission model |
| Commitments | ❌ MISSING | No commitment tracking |
| Organization dashboard | ❌ MISSING | No org-specific UI |
| Private state | ❌ MISSING | No private/public boundary |
| Publication mechanism | ❌ MISSING | No publish offer from private state |
| NGO agent | ❌ MISSING | No private AI agent |
| Permissions | ❌ MISSING | No auth/permission system |

Organizations exist only as flat records with `published_capabilities` and `public_contact`. There is no private state that the Network Agent cannot see.

---

## 10. SHARED VS PRIVATE DATA BOUNDARY

### Status: NOT ENFORCED

The current implementation has **no privacy boundary**:

- All data is accessible via all API endpoints
- Organizations are flat records — no concept of "my organization's private state"
- No authentication or authorization system
- The `published_capabilities` field exists but is not used for filtering
- Resource offers are public by design (the only way to share resources)
- No mechanism for an NGO to have private inventory that the Network cannot see

### Privacy Boundary Weakest Points:
1. All API endpoints are unauthenticated
2. No org-scoped data access
3. No private/public state separation
4. Frontend shows all data regardless of "viewer"

---

## 11. FIELD INTELLIGENCE AUDIT

### Implemented Components

| Component | Status | Location |
|-----------|--------|----------|
| Community report submission | ✅ | `community_reports.py` → `submit_report()` |
| KoboToolbox webhook | ✅ | `kobo_webhook_receiver.py` |
| Free-text extraction | ✅ | `field_intelligence_tool.py` → `extract_field_report()` |
| Field report storage | ✅ | JSON file (`data/community_reports.json`) |
| Override system | ✅ | `overrides.py` → `apply_override()` |
| Verification state | ✅ | `VerificationState` enum on FieldReport model |
| Report deduplication | ❌ | **NOT IMPLEMENTED** — 8 identical reports exist in `community_reports.json` |
| Evidence links | ❌ | Field reports don't link to Needs or Operations |
| UI display | ✅ | Field reports shown on map + in ContextPanel |

### Semantic Deduplication Status: **MISSING**
The `community_reports.json` contains 10 reports, many duplicates (e.g., "Road blocked near Jorhat due to flooding" appears 8 times). No deduplication exists.

---

## 12. DELTA / ATTENTION SYSTEM AUDIT

| Component | Status | Notes |
|-----------|--------|-------|
| Activity events | ✅ IMPLEMENTED | Append-only `activity_events` table + API |
| Activity bar | ✅ IMPLEMENTED | `ActivityBar.jsx` shows recent events with icons |
| What changed summary | ❌ MISSING | No delta computation (e.g., "+3 needs, -1 resolved") |
| Escalation/de-escalation | ❌ MISSING | No urgency change detection |
| Alert thresholds | ❌ MISSING | No threshold-based alerts |
| Semantic deduplication | ❌ MISSING | No dedup of field reports |
| Notifications | ✅ PARTIAL | `notifications` table exists, API exists, but no frontend notification panel |
| Live stream | ✅ PARTIAL | 30-second polling, but no real-time updates |

---

## 13. TEMPORAL DATA AUDIT

### Flood Snapshots
- **Multiple snapshots per district:** ✅ Supported (same district_id, different observed_at)
- **Temporal queries:** ✅ `list_flood_snapshots(district_id, observed_after)` + `get_latest_flood_snapshot(district_id, observed_at)`
- **Temporal filtering in planner:** ✅ Planner lists all snapshots per district with dates
- **Temporal UI controls:** ❌ **NOT IMPLEMENTED** — no time slider, no date picker, no temporal visualization
- **Flood change over time:** The planner's evidence includes `flood_snapshots` with dates, but no frontend visualization

### Current Data
Only Sivasagar has flood data (`sivasagar_flood.geojson`). GEE pipeline can generate flood data for other districts but requires manual execution.

---

## 14. EVIDENCE / PROVENANCE AUDIT

### Implemented

| Component | Status | Location |
|-----------|--------|----------|
| `Provenance` enum | ✅ | REAL, DERIVED, SYNTHETIC, MANUAL_OVERRIDE |
| Flood snapshot metadata | ✅ | source, confidence, provenance, source_timestamp on every snapshot |
| Field report source | ✅ | source_type, verification_state, extraction_confidence |
| Override tracking | ✅ | system_status vs override_status, actor, reason, timestamp |
| Planner uncertainty | ✅ | `PlanningResult.uncertainty` + `data_gaps` lists |
| Evidence panel (legacy) | ✅ | `EvidencePanel.jsx` shows flood/exposure/accessibility data |
| Evidence in context panel | ✅ | NeedDetail shows requested_resources, timestamps, activity |

### Not Implemented
- No evidence panel in the new workspace (replaced by ContextPanel dossiers)
- No explicit SOURCE/DATE/PROVENANCE/CONFIDENCE display on recommendations
- No uncertainty visualization in the new workspace

---

## 15. REAL DATA AUDIT

### File-Based Data (JSON)

| Dataset | Count | Notes |
|---------|-------|-------|
| `community_reports.json` | 10 reports | All from field_intelligence_text, most without coordinates |
| `overrides.json` | 7 overrides | 3 unique targets (Main Bridge Road, Blocked Road, Uncertain Road, Blocked Bridge) |
| `sivasagar_flood.geojson` | Sivasagar district | Sentinel-1 SAR flood polygons |
| `districts_gee.geojson` | District boundaries | Multiple districts |

### Database Data
Cannot query database directly (audit only), but based on test fixtures and API behavior:
- Districts: at least 4 (sivasagar, jorhat, charaideo, golaghat) based on test_planner.py
- Settlements: multiple per district
- Flood snapshots: at least 1 per district (Sivasagar has real data)
- Roads/Bridges: loaded from OSM PBF ingestion
- Medical facilities: loaded from OSM PBF ingestion

---

## 16. TEST AUDIT

### Test Files (23 detected)

| Test File | Category | Tests | Notes |
|-----------|----------|-------|-------|
| `test_planner.py` | Planner | Multiple | Cross-district, temporal, resource-aware, evidence, uncertainty |
| `test_ai_coordinator.py` | AI Coordinator | ~25 | Gap detection, duplicates, consequences, review targets, no-writes |
| `test_phase7b.py` | Collaboration | Multiple | Need/Offer/Operation lifecycle |
| `test_phase7d.py` | Operations | Multiple | Needs, offers, operations endpoints |
| `test_allocation.py` | Allocation | Multiple | PDC scoring, resource allocation |
| `test_assessment.py` | Assessment | Multiple | Assessment pipeline |
| `test_routing.py` | Routing | Multiple | OSRM routing |
| `test_override_routing.py` | Override Routing | Multiple | Override-aware routing |
| `test_flood_tool.py` | Flood Tool | Multiple | Flood status detection |
| `test_flood_pipeline.py` | GEE Pipeline | Multiple | Flood data pipeline |
| `test_community_reports.py` | Field Intelligence | Multiple | Community report submission |
| `test_verification.py` | Verification | Multiple | LLM extraction guardrails |
| `test_osm_pbf_ingestion.py` | Ingestion | Multiple | OSM PBF data loading |
| `test_export_district.py` | Export | Multiple | District data export |
| `test_priority.py` | Priority | Multiple | Priority scoring |
| `test_step1_multidistrict.py` | Multi-district | Multiple | Cross-district behavior |
| `test_phase3.py` | Phase 3 | Multiple | Generalized models |
| `test_phase4.py` | Phase 4 | Multiple | Repository-backed data |
| `test_postgres_repository.py` | PostgreSQL | Multiple | PostgresRepository tests |
| `test_agent_trace.py` | Agent Trace | Multiple | Agent timing trace |

### Test Architecture Notes
- Tests use `RELIEFOS_MEMORY=1` for InMemoryRepository
- Integration tests use `DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos`
- External services (Overpass, OSRM) are mocked in unit tests
- No E2E browser tests
- No frontend tests

---

## 17. DOCUMENTATION AUDIT

### DOCUMENTED BUT NOT IMPLEMENTED
- Network Main Agent with specialist workers (described in CLAUDE.md, not implemented)
- NGO Main Agent with private workers
- Private/public state boundary
- Temporal UI controls
- Command palette / search functionality
- Semantic deduplication
- Proactive AI alerts
- Responsive tablet/mobile layouts

### IMPLEMENTED BUT NOT DOCUMENTED
- `ai_coordinator.py` (read-only analysis) — no dedicated doc
- `matching.py` (deterministic matching) — no dedicated doc
- `verification.py` (LLM guardrails) — no dedicated doc
- Review targets on findings — no dedicated doc

### CONFLICTING DOCUMENTATION
- CLAUDE.md describes MapLibre/deck.gl, but code uses Leaflet
- CLAUDE.md describes dark blue-black (#05070A) background, code uses #0f1419
- CLAUDE.md describes JetBrains Mono + Inter fonts, code uses system fonts + Inter (not loaded)

---

## 18. DATA / RESOURCE / STORAGE AUDIT

### Required for Local Development
- PostgreSQL 16 + PostGIS 3.4 (via Docker Compose)
- OSRM routing server (via Docker Compose in `osrm/`)
- Ollama with llama3.2 (for LLM agents — optional, deterministic path works without it)
- Python dependencies (requirements.txt)

### Required for Runtime
- `data/sivasagar_flood.geojson` — flood polygons
- `data/overrides.json` — manual overrides
- `data/community_reports.json` — field reports
- `data/cache/` — Overpass API cache

### Optional / External
- Google Earth Engine credentials (for flood pipeline)
- KoboToolbox form (for webhook integration)
- OSM PBF files (for ingestion)

---

## 19. FINAL ARCHITECTURE GAP MATRIX

| Capability | Existing | Partial | Missing | Reuse | Redesign | Replace |
|------------|----------|---------|---------|-------|----------|---------|
| **UX / UI** | | | | | | |
| Map shell | ✅ | | | NetworkWorkspace | | |
| Left rail (layers) | ✅ | | | LayerRail | | |
| Right dossier panel | ✅ | | | ContextPanel | Refactor (duplicate code) | |
| Bottom delta bar | ✅ | | | ActivityBar | Add delta summary | |
| Command palette | | | ❌ | | | |
| Search | | | ❌ | WorkspaceHeader has UI shell | | |
| Temporal control | | | ❌ | | | |
| Responsive layout | | | ❌ | | | |
| Contextual selection | ✅ | | | Map → Panel sync | | |
| **Collaboration** | | | | | | |
| Needs | ✅ | | | Full CRUD + UI | | |
| Offers | ✅ | | | Full CRUD + UI | | |
| Matches | ✅ | | | Matching engine + UI | | |
| Operations | ✅ | | | Full CRUD + UI | | |
| Activity | ✅ | | | Activity events + ActivityBar | | |
| Notifications | | ✅ | | Table + API exist | Add frontend panel | |
| Community reports | ✅ | | | submit_report + field intelligence | | |
| **Intelligence** | | | | | | |
| Evidence | ✅ | | | Assessment pipeline | | |
| Delta | | | ❌ | | | |
| Deduplication | | | ❌ | | | |
| Temporal analysis | | ✅ | | Flood snapshots exist | Add UI | |
| Uncertainty | ✅ | | | Planner uncertainty lists | | |
| Proactive coordination | ✅ | | | AI coordinator findings | Wire to frontend | |
| **Agentic** | | | | | | |
| Network Main Agent | | | ❌ | | | |
| Network workers | | | ❌ | | | |
| NGO Main Agent | | | ❌ | | | |
| NGO workers | | | ❌ | | | |
| Cross-agent communication | | | ❌ | | | |
| Human approval | ✅ | | | Match confirmation | | |
| **Operational** | | | | | | |
| Resources | | | ❌ | | | |
| Teams | | | ❌ | | | |
| Routes | ✅ | | | OSRM routing | | |
| Access state | ✅ | | | Roads + overrides | | |
| Medical | ✅ | | | Medical facilities + accessibility | | |
| Field intelligence | ✅ | | | Reports + extraction | | |

---

## 20. FINAL TARGET ARCHITECTURE MAPPING

```
NETWORK
│
├── Network Main Agent                          ❌ MISSING
│   ├── Situation/Flood Worker                  ❌ MISSING
│   ├── Exposure Worker                         ❌ MISSING
│   ├── Medical Worker                          ❌ MISSING
│   ├── Logistics Worker                        ❌ MISSING
│   ├── Access/Routing Worker                   ❌ MISSING
│   ├── Field Intelligence Worker               ❌ MISSING
│   ├── Coordination Worker                     ❌ MISSING
│   └── Evidence Worker                         ❌ MISSING
│
└── SHARED OPERATIONAL STATE
    ├── Needs                                   ✅ EXISTS (models, repo, API, UI)
    ├── Incidents                               ❌ MISSING (no model, no UI)
    ├── Resource Offers                         ✅ EXISTS (models, repo, API, UI)
    ├── Organizations                           ✅ EXISTS (models, repo, API) — no UI dossier
    ├── Operations                              ✅ EXISTS (models, repo, API, UI)
    ├── Tasks                                   ❌ MISSING (no model)
    ├── Field Reports                           ✅ EXISTS (models, repo, API, UI)
    ├── Overrides                               ✅ EXISTS (models, repo, API, UI)
    ├── Evidence                                ✅ EXISTS (assessment pipeline)
    ├── Notifications                           ✅ EXISTS (models, repo, API) — no UI panel
    └── Activity                                ✅ EXISTS (models, repo, API, UI)

NGO
│
├── NGO Main Agent                              ❌ MISSING
│   ├── Inventory Worker                        ❌ MISSING
│   ├── Logistics Worker                        ❌ MISSING
│   ├── Team Worker                             ❌ MISSING
│   ├── Mission Worker                          ❌ MISSING
│   └── Field Worker                            ❌ MISSING
│
└── PRIVATE ORGANIZATIONAL STATE                ❌ MISSING
```

---

## 21. FINAL UI ARCHITECTURE MAPPING

```
TARGET                          ACTUAL                          STATUS

TOP BAR
├── ReliefOS identity           ✅ WorkspaceHeader              EXISTS
├── Response selector           ✅ District dropdown             EXISTS
├── Network/org mode            ❌ Not implemented              MISSING
├── Time                        ❌ Not implemented              MISSING
├── Connection status           ✅ "System Active" indicator    EXISTS
└── Command/search              ⚠️ UI shell only, non-functional PARTIAL

LEFT RAIL
├── Hazard (flood)              ✅ LayerRail                    EXISTS
├── Infrastructure (roads/bridges/buildings/medical) ✅         EXISTS
├── Response (needs/operations/offers) ✅                       EXISTS
└── Intelligence (reports/overrides/AI alerts) ✅               EXISTS

CENTER
└── Persistent operational map  ✅ MapCanvas (Leaflet)          EXISTS (needs MapLibre migration)

RIGHT RAIL
├── Selected object dossier     ✅ ContextPanel                 EXISTS (needs refactor)
├── AI coordinator              ⚠️ Button exists, panel missing PARTIAL
├── Evidence                    ⚠️ In dossier, not standalone   PARTIAL
└── Contextual actions          ✅ Actions in dossiers          EXISTS

BOTTOM BAR
├── What changed                ❌ No delta summary             MISSING
├── Live activity               ✅ ActivityBar                  EXISTS
└── Status                      ✅ Critical needs indicator     EXISTS
```

---

## 22. FINAL IMPLEMENTATION ORDER

### P0 — Prerequisites (must do first)
1. **Wire AI Coordinator findings to frontend** — Backend endpoint exists, frontend never calls it. Connect to ActivityBar and ContextPanel.

### P1 — Highest Priority
2. **Refactor ContextPanel** — Remove duplicate code blocks (~600 lines of duplication). Extract NeedDetail, OperationDetail, etc. into separate components.
3. **Add Organization detail panel** — Organizations exist in the system but have no dossier panel.
4. **Wire notification panel** — Backend + API exist, frontend has no notification panel.

### P2 — Next Priority
5. **NGO workspace (minimal)** — Add organization-scoped views, resource inventory model, and publication mechanism.
6. **Delta/attention system** — Compute and display what changed since last view.
7. **Temporal UI controls** — Time slider or date picker for flood snapshot selection.
8. **Search functionality** — Implement the command palette that the WorkspaceHeader shell already has.

### P3 — Later
9. **MapLibre/deck.gl migration** — Replace Leaflet with MapLibre as specified in CLAUDE.md.
10. **Network Main Agent** — Implement hierarchical agent orchestration.
11. **NGO Main Agent** — Private workspace intelligence.
12. **Semantic deduplication** — Merge similar field reports.
13. **Responsive layouts** — Tablet and mobile support.
14. **Authentication/permissions** — User accounts and org-scoped access.

### Code to Preserve
- All `agent/data/models.py` dataclasses
- All `agent/data/repository.py` interface + implementations
- `agent/matching.py` matching engine
- `agent/ai_coordinator.py` analysis engine
- `agent/planner.py` planner orchestrator
- All API endpoints in `agent/api.py`
- `frontend/src/components/workspace/MapCanvas.jsx`
- `frontend/src/components/workspace/LayerRail.jsx`
- `frontend/src/components/workspace/ActivityBar.jsx`
- `frontend/src/lib/workspaceContext.jsx`

### Code to Refactor
- `frontend/src/components/workspace/ContextPanel.jsx` — Extract sub-components, remove duplication

### Code to Leave Untouched
- All test files
- All ingestion scripts
- GEE pipeline
- OSRM configuration
- Docker Compose

---

## 23. EXPLICIT NON-GOALS (DO NOT)

Per the audit instructions and CLAUDE.md:

- ❌ DO NOT implement the UI (this is an audit)
- ❌ DO NOT create new database migrations
- ❌ DO NOT rewrite planner.py
- ❌ DO NOT create fake resources
- ❌ DO NOT hardcode historical incidents
- ❌ DO NOT hardcode district logic
- ❌ DO NOT delete existing functionality
- ❌ DO NOT modify Docker
- ❌ DO NOT ingest new data
- ❌ DO NOT redesign routing
- ❌ DO NOT introduce autonomous agent matching
- ❌ DO NOT change real flood data
- ❌ DO NOT truncate the database
- ❌ DO NOT change production behavior

---

## 24. VALIDATION

### Files Modified
None (audit only)

### Files Created
None (audit only)

### Database Modified: NO
### Docker Modified: NO
### Data Modified: NO

---

## FINAL REPORT

### What is genuinely already built:
- Complete data model with 16 domain classes and 14 database tables
- Full repository pattern (InMemory + PostgreSQL)
- End-to-end collaboration lifecycle (Need → Offer → Match → Confirm → Operation → Resolve)
- Map-first workspace with 13 layer types, context panel, activity bar
- Deterministic planning engine (cross-district, temporal, resource-aware)
- AI coordinator with 3 detectors (gaps, duplicates, consequences)
- OSRM routing with override awareness
- Field intelligence pipeline (community reports + KoboToolbox + free-text extraction)
- Override system with system_status vs override_status
- Activity event logging
- 4 Strands LLM agents (coordinator, flood, accessibility, supply matching)
- ~20 test files covering core functionality

### What is only conceptual:
- Network Main Agent (hierarchical orchestration)
- NGO Main Agent + private workspace
- Private/public state boundary
- Specialist worker agents (situation, exposure, medical, logistics, access, field, coordination, evidence)
- Temporal UI controls
- Command palette / search
- Semantic deduplication
- Proactive AI alerts
- Responsive layouts

### What is partially connected:
- AI Coordinator findings (backend works, frontend doesn't call it)
- Notifications (backend + API exist, no frontend panel)
- Organization records (CRUD exists, no dossier panel)
- Search (UI shell exists in WorkspaceHeader, not functional)

### What the largest frontend gap is:
The `ContextPanel.jsx` is ~2000 lines with **duplicated code blocks** (NeedDetail appears twice with slight variations). It also lacks an AI analysis panel and Organization dossier.

### What the largest backend/agent gap is:
The **NGO workspace** is completely absent. No private state, no resource inventory, no teams, no missions, no publication mechanism. Organizations are flat records.

### What the minimum next implementation step is:
Wire the existing `/api/ai-coordinator/analysis` endpoint to the frontend. The backend returns structured findings with `review_target` objects that tell the frontend exactly which panel to open and where to fly the map.

### What NOT to rebuild:
- Data models, repository pattern, matching engine, activity events, override system, planning engine, map layers, context panel dossiers
