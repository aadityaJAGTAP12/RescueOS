# ReliefOS

A multi-agent disaster-response framework that prioritizes rescue operations using real flood data, building exposure analysis, medical facility accessibility scoring, OSRM routing with flood-aware intersection detection, and community field intelligence.

**Generalization is a hard requirement.** ReliefOS must work across different districts, flood events, dates, infrastructure, and resource constraints without district-specific branching. The 2026 Assam flood scenarios (Sivasagar, Jorhat, Charaideo) are retrospective validation cases — they must not become hardcoded application logic.

## Current Statuscf 

| Milestone | Status |
|---|---|
| Phase 1 — Multi-agent architecture | ✅ Complete |
| Phase 2 — Flood-aware routing + community reports + frontend | ✅ Complete |
| Phase 3 — Generalized, scenario-independent data foundation | ✅ Complete |
| Phase 4 — Rewire runtime to generalized data layer | ✅ Complete |
| Phase 5A — PostgreSQL + PostGIS production data layer | ✅ Complete |
| Test suite | 182 tests passing (24 DB integration tests require PostgreSQL) |

## Architecture

ReliefOS uses a modular multi-agent architecture built on the [Strands SDK](https://github.com/strands-agents/sdk-python):

```
agent/
├── config.py                          # Model provider, constants, known locations
├── data_loader.py                     # Flood polygon loading, haversine, caching
├── main.py                            # Entry point (ranking + allocation demo)
├── api.py                             # Flask API (port 5001) — primary backend
├── assessment.py                      # run_relief_assessment() — orchestrator
├── community_reports.py               # Community report CRUD (JSON storage)
├── overrides.py                       # Manual status override system
├── verification.py                    # LLM extraction guardrails
│
├── tools/                             # Pure functions (testable, deterministic)
│   ├── flood_tool.py                  # Flood detection against Sentinel-1 GeoJSON
│   ├── exposure_tool.py               # Building exposure counting within flood zones
│   ├── accessibility_tool.py          # Medical facility proximity via Overpass API
│   ├── allocation_tool.py             # PDC scoring, ranking, greedy allocation
│   ├── routing_tool.py                # OSRM routing + flood-route intersection detection
│   ├── road_status_tool.py            # Road flood check (exists, not in deterministic runtime)
│   ├── region_scan_tool.py            # Grid-based flood area scanning
│   ├── field_intelligence_tool.py     # LLM extraction from raw field observations
│   └── query_parser_tool.py           # LLM parsing of free-text coordinator queries
│
├── agents/                            # Strands Agent reasoning components
│   ├── coordinator_agent.py           # Top-level orchestration of all sub-agents
│   ├── flood_assessment_agent.py      # Flood + building exposure reasoning
│   ├── accessibility_agent.py         # Medical accessibility reasoning
│   ├── allocation_agent.py            # Priority computation reasoning
│   └── supply_matching_agent.py       # Supply matching reasoning
│
├── tools/                             # Tool functions
│   ├── ...
│
├── data/
│   ├── sivasagar_flood.geojson        # Sentinel-1 flood polygons (static)
│   ├── community_reports.json         # Stored community reports
│   ├── overrides.json                 # Manual status overrides
│   └── cache/                         # Overpass API cache files
│       ├── accessibility_*.json
│       ├── buildings_*.json
│       └── roads_*.json
│
├── osrm/                              # Local OSRM routing server config
│   ├── docker-compose.yml
│   ├── setup.sh
│   └── README.md
│
├── frontend/                          # React/Vite/Tailwind UI
│   ├── src/
│   │   ├── App.jsx                    # Main app with routing
│   │   └── components/
│   │       ├── QueryInput.jsx         # Free-text query interface
│   │       ├── SituationMap.jsx       # Leaflet flood map visualization
│   │       ├── OperationalAnswer.jsx  # Assessment result display
│   │       ├── StagedReveal.jsx       # Progressive data reveal animation
│   │       ├── EvidenceCard.jsx       # Evidence display cards
│   │       ├── EvidencePanel.jsx      # Evidence aggregation panel
│   │       ├── DataGapsPanel.jsx      # Missing data indicators
│   │       ├── FieldIntelligencePage.jsx # Field report submission
│   │       ├── Header.jsx             # App header
│   │       └── LocationSelector.jsx   # Location picker
│
├── tests/                             # 114 tests
│   ├── conftest.py
│   ├── test_routing.py                # OSRM routing + flood intersection
│   ├── test_priority.py               # PDC scoring
│   ├── test_allocation.py             # Resource allocation
│   ├── test_assessment.py             # Assessment orchestration
│   ├── test_flood_tool.py             # Flood detection
│   ├── test_community_reports.py      # Community report storage
│   ├── test_verification.py           # LLM guardrails
│   └── test_agent_trace.py            # Agent trace verification
│
├── kobo_webhook_receiver.py           # Separate Flask app (port 5000) for KoboToolbox
├── test_kobo_webhook_locally.py       # Local Kobo webhook testing
└── requirements.txt
```

### Design Decisions

- **Model Provider Isolation**: All model-specific code lives in `config.py`. Switch from Ollama to AWS Bedrock by changing only that file.
- **Tool Composition over Agent.run()**: Strands Agent objects don't expose a `.run()` method. Agent tools call other `@tool` functions directly and compose results in Python — guaranteeing execution order with no step-skipping.
- **Cache-First Pattern**: Overpass API responses are cached locally in `data/cache/` to avoid rate limits and enable offline testing.
- **Honest Error Handling**: API timeouts and missing data are returned as explicit uncertainty states, not silent failures. Scoring treats unknown data conservatively.
- **Deterministic + LLM paths**: The assessment pipeline has a fully deterministic path (flood detection, exposure, accessibility, PDC, allocation) that works without any LLM. LLM agents provide synthesis/reasoning on top.
- **Flood-aware routing**: OSRM routing uses `overview=full` to get complete geometry, then checks flood-polygon intersection via Shapely. Haversine fallback for when OSRM is unavailable.

### PDC Scoring Formula

```
PDC = 0.35 × building_exposure + 0.35 × flood_polygon_scale + 0.30 × medical_accessibility
```

PDC components are normalized 0–1. Locations are classified:
- PDC ≥ 0.5 → **PRIORITY**
- PDC ≥ 0.3 → **EXPOSED**
- PDC < 0.3 → **SAFE**

### Flood Detection Semantics

`flood_tool.py` classifies point locations as:
- **exactly contained** — point is inside a flood polygon
- **near flood zone** — point is within flood threshold distance of a polygon
- **flooded** — either of the above
- **nearest flood polygon** — distance to closest polygon returned

### Routing + Flood Intersection

`routing_tool.py` implements:
1. OSRM route request with `overview=full`, `geometries=geojson`, `steps=true`
2. Route geometry extracted from OSRM response
3. `check_route_flood_intersection()` — tests if route geometry intersects any flood polygon via Shapely
4. Haversine fallback — 2-point straight-line geometry when OSRM is unavailable (source labeled as `"straight-line (haversine)"`)
5. `get_multiple_routes()` — generates route variants for comparison
6. `get_route_for_allocation()` — route-aware allocation helper

## Running

```bash
# Main demo: rank 3 known locations + allocate resources
python agent/main.py

# Flask API (port 5001)
python -m agent.api

# React frontend (port 3000)
cd frontend && npm run dev

# All 182 tests (no Ollama required, no DB required)
python -m pytest -v
```

### Phase 5A: PostgreSQL + PostGIS Setup

ReliefOS now supports PostgreSQL + PostGIS as a production data layer.

```bash
# 1. Start PostgreSQL + PostGIS (Docker)
docker compose up -d

# 2. Set DATABASE_URL
export DATABASE_URL=postgresql://reliefos:reliefos@localhost:5432/reliefos

# 3. Initialize database schema + import data
python scripts/db_init.py

# 4. Run API with PostgreSQL backend
python -m agent.api

# 5. Run DB integration tests (24 tests)
pytest tests/test_postgres_repository.py -v

# 6. Force in-memory mode (for tests)
export RELIEFOS_MEMORY=1
python -m pytest tests/ -v
```

**Without PostgreSQL:** The application falls back to InMemoryRepository automatically.
All 182 existing tests pass without any database.

**With PostgreSQL:** Set `DATABASE_URL` and the application uses PostgresRepository.
24 additional DB integration tests become available.

### URLs

| Service | URL | Purpose |
|---|---|---|
| Frontend | http://localhost:3000 | Dashboard, query, map, field intelligence |
| API | http://localhost:5001 | All backend endpoints |
| Ollama | http://localhost:11434 | LLM inference (llama3.2) |

### API Endpoints

```
GET  /api/locations                    → known locations list
GET  /api/assess?location=<name>       → full assessment (named)
GET  /api/assess?lat=<lat>&lon=<lon>   → full assessment (coordinates)
GET  /api/flood-geojson                → flood polygon data for map
POST /api/query                        → free-text query → parsed + assessed
POST /api/field-intelligence           → raw text → extracted structured fields
GET  /api/field-intelligence/history   → all field reports
POST /api/override                     → create manual status override
GET  /api/override/status              → check override for target
GET  /api/overrides                    → all active overrides
POST /api/community-reports            → submit community report
GET  /api/community-reports            → list community reports
GET  /api/route                        → OSRM route between two points
GET  /api/route/multiple               → multiple route variants
POST /api/route/for-allocation         → route-aware allocation
```

## Data Sources

| Source | File/Service | Status | Usage |
|---|---|---|---|
| Sentinel-1 flood polygons | `data/sivasagar_flood.geojson`, `data/raw/floods/` | Static, local | Flood detection |
| Overpass API (buildings, roads, medical) | Live + `data/cache/` | Cache-first | Infrastructure data |
| OSRM routing | Local Docker (`localhost:5000`) | Live, local | Route geometry |
| Ollama (llama3.2) | `localhost:11434` | Live, local | Query parsing, field extraction |
| Regional OSM PBF | `data/raw/osm/north-eastern-zone-latest.osm.pbf` | External source, not in Git | OSRM routing, infrastructure |
| Manual overrides | `data/overrides.json` | JSON file | Operational status overrides |

**NOT yet integrated:** Google Flood Forecasting, CWC/India-WRIS, NASA, Earth Engine, WorldPop, GADM, KoboToolbox (webhook exists but separate app).

## External Service Integrations

| Service | Status |
|---|---|
| **Ollama** | ✅ Implemented and used (query parsing, field intelligence, LLM synthesis) |
| **Strands SDK** | ✅ Implemented and used (agent framework) |
| **OSRM** | ✅ Implemented and used (local Docker, flood-aware routing) |
| **Overpass API** | ✅ Implemented and used (buildings, roads, medical facilities) |
| **Flask** | ✅ Implemented and used (API backend, port 5001) |
| **KoboToolbox** | ⚠️ Webhook receiver exists (`kobo_webhook_receiver.py`) but runs as separate Flask app on port 5000 |
| **Cloudflare Tunnel** | ⚠️ `cloudflared.exe.exe` in repo root — only needed for live Kobo webhook testing |
| **AWS Bedrock** | ❌ Not yet migrated (planned for future phase) |
| **PostgreSQL/PostGIS** | ✅ Implemented (Phase 5A, requires DATABASE_URL env var) |
| **Earth Engine** | ❌ Not integrated (source of flood GeoJSON export) |

## Phase History

### Phase 1 — Multi-Agent Architecture (Complete)
- Monolithic → multi-agent Strands architecture
- Deterministic tool pipeline: flood → exposure → accessibility → PDC → allocation
- LLM synthesis via coordinator agent
- 20 tests

### Phase 2 — Flood-Aware Routing + Community Reports + Frontend (Complete)
- OSRM routing with `overview=full` geometry
- Flood-route intersection detection (Shapely)
- Community report storage and retrieval
- Local override system
- Field intelligence extraction (LLM)
- Free-text query parsing (LLM)
- React/Vite/Tailwind frontend with Leaflet map
- Flask API backend
- KoboToolbox webhook receiver
- Route geometry regression test (`overview=full` verification)
- Grew to 114 tests

### Phase 3 — Generalized Data Foundation (Complete)
- Generalized data models (District, Settlement, FloodSnapshot, Building, etc.)
- Abstract DataRepository interface + InMemoryRepository
- Data migration layer (import from JSON/GeoJSON)
- Multi-district test fixtures
- Provenance model (REAL / DERIVED / SYNTHETIC / MANUAL_OVERRIDE)
- 182 tests passing

### Phase 4 — Rewire Runtime to Generalized Layer (Complete)
- Tools read data through DataRepository abstraction
- Repository-aware data loading functions
- Flood, exposure, accessibility tools use repository
- District-independent assessment code
- Sivasagar regression preserved

### Phase 5A — PostgreSQL + PostGIS Production Data Layer (Complete)
- PostgreSQL + PostGIS via SQLAlchemy Core + GeoAlchemy2
- Full PostgresRepository implementing DataRepository interface
- Database schema: districts, settlements, flood_snapshots, field_reports, overrides, buildings, medical_facilities, roads
- Spatial indexes (GiST) on all geometry columns
- Database-side spatial filtering (point-in-polygon, intersects, within radius)
- Temporal flood snapshot queries
- Repository factory: auto-selects based on DATABASE_URL env var
- Docker Compose for local PostgreSQL + PostGIS
- DB initialization script + data migration
- 24 PostgreSQL integration tests
- Generalization acceptance test
- Legacy fallback preserved (InMemoryRepository when no DB)
- Must preserve all Phase 1-4 behavior

## Key Constraints

1. **Generalization is mandatory.** No district-specific if/else, no hardcoded scenario IDs, no prewritten answers for known incidents.
2. **Don't break existing behavior.** `python agent/main.py`, `python -m agent.api`, all 114 tests must keep passing.
3. **Deterministic path must work without LLM.** Assessment, PDC, allocation run without Ollama.
4. **Don't overbuild.** Phase 3 establishes schemas and access layers — not full multi-district ingestion, not cloud deployment, not voice/WhatsApp.
5. **Don't redesign PDC/ranking/allocation.** Only generalize their input data sources over time.
6. **Don't require live services for tests.** Overpass, Ollama, OSRM, internet — none required for unit tests.

## Known Technical Debt

1. Kobo webhook receiver is a separate Flask app (port 5000) — should be integrated into main API
2. `allocation_agent_tool` and `coordinator_agent_tool` defined but unused by any runtime path
3. Road status tool exists but is not accessible from the deterministic runtime
4. `allocate_resources()` returns a formatted string, not structured data
5. All data storage is JSON files — no database
6. Flood GeoJSON is static — no update mechanism
7. No authentication or rate limiting on any API endpoint
8. `cloudflared.exe.exe` binary in repo root

## Important Files (Top 20)

| # | File | Why it matters |
|---|---|---|
| 1 | `agent/assessment.py` | Core orchestrator — `run_relief_assessment()` |
| 2 | `agent/api.py` | Flask API — all backend endpoints |
| 3 | `agent/config.py` | Model config, known locations, Overpass config |
| 4 | `agent/data_loader.py` | Flood data loading, haversine, cache management |
| 5 | `agent/tools/flood_tool.py` | Flood detection against GeoJSON polygons |
| 6 | `agent/tools/exposure_tool.py` | Building exposure within flood zones |
| 7 | `agent/tools/accessibility_tool.py` | Medical facility proximity scoring |
| 8 | `agent/tools/allocation_tool.py` | PDC, ranking, greedy allocation |
| 9 | `agent/tools/routing_tool.py` | OSRM routing + flood intersection detection |
| 10 | `agent/tools/query_parser_tool.py` | LLM query parsing |
| 11 | `agent/tools/field_intelligence_tool.py` | LLM field observation extraction |
| 12 | `agent/agents/coordinator_agent.py` | Top-level LLM orchestration |
| 13 | `agent/community_reports.py` | Community report storage |
| 14 | `agent/overrides.py` | Manual status override system |
| 15 | `agent/verification.py` | LLM extraction guardrails |
| 16 | `data/sivasagar_flood.geojson` | Sentinel-1 flood polygons (sole flood data) |
| 17 | `tests/test_routing.py` | OSRM routing + overview=full regression test |
| 18 | `frontend/src/App.jsx` | Main React app |
| 19 | `frontend/src/components/SituationMap.jsx` | Leaflet flood map |
| 20 | `requirements.txt` | Runtime dependencies |

## Running Tests

```bash
# Full suite (182 tests, no external services required)
python -m pytest -v

# Specific areas
python -m pytest tests/test_routing.py -v        # routing + flood intersection
python -m pytest tests/test_priority.py -v       # PDC scoring
python -m pytest tests/test_allocation.py -v     # resource allocation
python -m pytest tests/test_assessment.py -v     # assessment orchestration
python -m pytest tests/test_flood_tool.py -v     # flood detection
python -m pytest tests/test_community_reports.py -v  # community reports
python -m pytest tests/test_verification.py -v   # LLM guardrails
python -m pytest tests/test_phase3.py -v         # generalized data foundation
python -m pytest tests/test_phase4.py -v         # runtime rewired to repository

# PostgreSQL integration tests (requires DATABASE_URL)
export DATABASE_URL=postgresql://reliefos:reliefos@localhost:5432/reliefos
pytest tests/test_postgres_repository.py -v
```
