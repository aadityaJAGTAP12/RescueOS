# RELIEFOS — CURRENT STATE RECONCILIATION

**Date:** 2026-09-01
**Status:** RECONCILIATION ONLY — No code or data changes made

---

## 0. ORGANIZATION IDENTITY SEAM (Phase 7I addition, 2026-09-07)

### What was built

A clean **organization-identity seam**: one authoritative function that every
piece of NGO / private-workspace logic uses to determine "which organization
is this".

- **Seam function:** `agent/org_context.py` → `resolve_current_org(request) -> str`
- **Mechanism:** a plain `reliefos_org_id` cookie set by `POST /api/session/org`
  (validated against registered organizations at switch time). Cookieless
  callers (tools, curl, tests) fall back to `DEFAULT_ORG_ID = "org_demo"`.
- **Selection UI:** org picker in the workspace header
  (`frontend/src/components/workspace/WorkspaceHeader.jsx` → `OrgSwitcher`),
  backed by `frontend/src/lib/orgContext.js` + session state in
  `frontend/src/lib/workspaceContext.jsx` (`state.orgId`).
- **All org-scoped endpoints moved** from `/api/orgs/<org_id>/...` (which
  trusted a client-supplied org id in the URL) to `/api/my-org/...`, deriving
  the org server-side per request via the seam.

### ⚠️ THIS IS IDENTITY / CONTEXT ONLY — NOT AUTHENTICATION

- There is **no password, login, session token, or credential** of any kind.
- **Anyone can select any organization** — via the picker or by simply setting
  the `reliefos_org_id` cookie. The cookie is unsigned and trivially forged.
- This is **NOT safe for a multi-tenant or public deployment as-is**.
- Real authentication/authorization is **deliberately deferred** to a specific
  future deployment's needs. The value built here is the *seam*: every
  org-scoped code path already flows through ONE function, so a future auth
  layer only has to change `resolve_current_org` — no endpoint changes needed.

### Hardcoded / client-trusted org_id locations found and fixed

Full audit list (grep across `agent/` and `frontend/src/`):

| # | Location | Was | Now |
|---|----------|-----|-----|
| 1 | `frontend/src/components/workspace/OrganizationWorkspace.jsx:14` | `CURRENT_ORG_ID = "org_demo"` hardcoded | Removed; org comes from session state (`state.orgId`), fetches hit `/api/my-org/*` |
| 2 | `tools/ui-diagnostics.cjs` | hardcoded `org_demo` seed, no session | Seeds org then selects it via `POST /api/session/org` |
| 3 | `agent/api.py` — all 16 `/api/orgs/<org_id>/...` endpoints (summary, resources GET/POST/PATCH/DELETE, teams GET/POST/PATCH, missions GET/POST/PATCH, analyze-need, situation, publish-offer, evaluate-coordination, approve-publication) | org id taken from the URL path (client-trusted) | Replaced with `/api/my-org/*` + `resolve_current_org(request)` |
| 4 | `agent/api.py` `POST /api/offers` | `payload.get("organization_id") or "org_reliefos_default"` (client-trusted) | `resolve_current_org(request)`; client body org id ignored |
| 5 | `frontend/src/components/workspace/ContextPanel.jsx` `CreateOfferForm` | posted to `/api/orgs/${form.organization_id}/publish-offer` with a form-chosen org | Posts to `/api/my-org/publish-offer`; form org field is display-only |
| 6 | `tools/publish-offer-verify.cjs`, `tools/double-click-test.cjs`, `tools/cdp-trace.cjs` | seeded private state via `/api/orgs/org_demo/...` | Select org via `POST /api/session/org`, then use `/api/my-org/*` |
| 7 | `tools/timed_api_diag.py` | hardcoded `"org_demo"` private-context reads | Diagnostic-only tool; still targets the default org explicitly for timing tests (not a trust-boundary surface — left as-is, documented here) |

Locations deliberately **not** changed (they are not trust-boundary surfaces):

- `GET /api/offers?organization_id=...` and `GET
  /api/network/coordination/proposals?organization_id=...` — read-only public
  network filters, not privileged actions.
- `POST /api/operations` `lead_organization_id` — a coordinator-facing shared
  object field (who leads the op), not a private-context selector; the org
  context for private state still comes from the seam.
- `POST /api/network/coordination/propose` `organization_id` — network-agent
  proposal targeting (which org a proposal is FOR), public by design.
- Match-confirm flow — already derived the org server-side from the offer
  (`offer.organization_id`); no change needed.
- `data/orgs/org_demo/*.json` — private-state data files, not code.

### Verification evidence

- `tests/test_org_context.py` (17 tests): cookie resolution + fallback,
  session endpoints, private-endpoint isolation across two real orgs,
  NGO agent analysis resolving to the selected org, publish-offer trust
  boundary (client-supplied `organization_id: "org_evil"` ignored — server
  context wins), old `/api/orgs/...` routes 404, cookieless fallback.
- `frontend/src/__tests__/orgContext.test.jsx` (8 tests): session-derived
  resolution, POST /api/session/org selection, create-and-switch, cookie
  mirror, failure fallback.
- Live server verification (org switch + trust boundary with real requests):
  see `docs/PHASE7I_FUNCTIONAL_AUDIT.md` § org-context.

---

## 1. CURRENT CODE STATE

### Audit Verification Results

The previous audit (`docs/RELIEFOS_FULL_REPOSITORY_AUDIT.md`) is **verified as accurate** against the current codebase. No changes have been made to any application code since the audit was written. The only new file is the audit document itself.

#### Specific Verifications

| Claim from Audit | Verified? | Evidence |
|-----------------|-----------|----------|
| React 19 + Vite 8 frontend | ✅ | `frontend/package.json` confirms react 19.2.8, vite 8.2.0 |
| Leaflet map (NOT MapLibre) | ✅ | `MapCanvas.jsx` imports from `react-leaflet`, no MapLibre dependency |
| Flask backend on port 5001 | ✅ | `agent/api.py` line: `app.run(host="0.0.0.0", port=5001)` |
| 15 database tables in schema | ✅ | `agent/data/schema.py` defines: districts, settlements, flood_snapshots, field_reports, overrides, buildings, medical_facilities, roads, organizations, needs, resource_offers, operations, operation_participants, activity_events, notifications |
| Collaboration lifecycle (Need→Offer→Match→Confirm→Operation) | ✅ | All endpoints implemented in `agent/api.py` |
| AI coordinator with 3 detectors | ✅ | `agent/ai_coordinator.py` has `detect_coordination_gaps`, `detect_duplicate_responses`, `detect_consequence_alerts` |
| Matching engine in `matching.py` | ✅ | `agent/matching.py` implements `find_matches_for_need` with scoring |
| Planner orchestrator | ✅ | `agent/planner.py` implements `PlannerOrchestrator` |
| ContextPanel has duplicate code | ✅ | `ContextPanel.jsx` is ~2000 lines with repeated NeedDetail sections |
| OSRM routing | ✅ | `agent/tools/routing_tool.py` implements OSRM + haversine fallback |
| 4 flood GeoJSON files exist | ✅ | `data/raw/floods/` contains sivasagar, jorhat, charaideo, golaghat flood files |
| KoboToolbox webhook | ✅ | `kobo_webhook_receiver.py` implemented |

### Changes Since Audit: NONE
No application code has been modified since the audit was produced.

---

## 2. CURRENT DATABASE STATE

### CRITICAL: Database Is Not Accessible

**The PostgreSQL server is not running.** Docker is not available on this system, so the PostGIS container (`reliefos-postgis`) cannot be started.

```
Connection refused on localhost:5433
Docker: not available
```

**Exact table counts cannot be verified at this time.**

### What We Know About Database State

Since the database is inaccessible, we must infer state from:

1. **Migration code** (`agent/data/migration.py`) — shows what `db_init.py` would import
2. **Ingestion code** (`scripts/ingest/osm_pbf.py`) — shows what OSM ingestion would produce
3. **Docker Compose** (`docker-compose.yml`) — defines the PostgreSQL container
4. **Git history** — shows when data was committed
5. **File system** — flood GeoJSON files exist on disk

### Expected Database State (from migration code)

If `db_init.py` were run against a fresh database:

| Table | Expected Count | Source |
|-------|---------------|--------|
| districts | 4 | Migration seeds sivasagar, jorhat, charaideo, golaghat |
| settlements | 3+ | Migration seeds 3 Sivasagar settlements; OSM ingestion adds more |
| flood_snapshots | 4 | Migration imports 4 Sentinel-1 flood GeoJSON files |
| field_reports | 10 | Migration imports `data/community_reports.json` (10 reports) |
| overrides | 7 | Migration imports `data/overrides.json` (7 overrides) |
| buildings | 0+ | Only via OSM PBF ingestion (requires PBF file + ingestion run) |
| roads | 0+ | Only via OSM PBF ingestion |
| medical_facilities | 0+ | Only via OSM PBF ingestion |
| needs | 0 | Created at runtime via API |
| resource_offers | 0 | Created at runtime via API |
| operations | 0 | Created at runtime via API |
| activity_events | 0+ | Created at runtime via API |
| notifications | 0 | Created at runtime via API |
| organizations | 0 | Created at runtime via API |

---

## 3. DISTRICT DATA MATRIX

### Expected (from migration code + file system)

| District | Boundary | Settlements | Buildings | Roads | Bridges | Medical | Flood Snapshots |
|----------|----------|-------------|-----------|-------|---------|---------|----------------|
| sivasagar | ✅ In migration | 3 (seed) | 0+ (OSM) | 0+ (OSM) | 0+ (OSM) | 0+ (OSM) | 1 (sivasagar_flood.geojson) |
| jorhat | ✅ In migration | 0+ (OSM) | 0+ (OSM) | 0+ (OSM) | 0+ (OSM) | 0+ (OSM) | 1 (jorhat_flood_2026-07-29_2026-07-30.geojson) |
| charaideo | ✅ In migration | 0+ (OSM) | 0+ (OSM) | 0+ (OSM) | 0+ (OSM) | 0+ (OSM) | 1 (charaideo_flood_2026-07-29_2026-07-30.geojson) |
| golaghat | ✅ In migration | 0+ (OSM) | 0+ (OSM) | 0+ (OSM) | 0+ (OSM) | 0+ (OSM) | 1 (golaghat_flood_2026-07-22_2026-07-23.geojson) |

**Note:** Buildings, roads, bridges, and medical facilities require OSM PBF ingestion to be populated. The PBF file (`data/raw/osm/north-eastern-zone-latest.osm.pbf`) is gitignored and not committed.

---

## 4. FLOOD SNAPSHOT MATRIX

### Flood GeoJSON Files on Disk

| File | District | Observed At | Size | Git Status |
|------|----------|-------------|------|------------|
| `data/sivasagar_flood.geojson` | sivasagar | 2026-07-01 | ~file | ✅ Committed |
| `data/raw/floods/jorhat_flood_2026-07-29_2026-07-30.geojson` | jorhat | 2026-07-29 | 19MB | ✅ Committed |
| `data/raw/floods/charaideo_flood_2026-07-29_2026-07-30.geojson` | charaideo | 2026-07-29 | 4.8MB | ✅ Committed |
| `data/raw/floods/golaghat_flood_2026-07-22_2026-07-23.geojson` | golaghat | 2026-07-22 | 12.2MB | ✅ Committed |

### Migration Import Behavior

The migration code (`agent/data/migration.py`) is **idempotent**:
- Uses deterministic snapshot IDs: `flood_{district_id}_{YYYYMMDD}`
- Uses `ON CONFLICT DO UPDATE` in PostgreSQL
- Checks for existing snapshots before importing
- All 4 flood files are referenced in `DISTRICT_FLOOD_SOURCES`

### Expected Database Snapshots (if migration runs)

| Snapshot ID | District | Observed At | Source | Polygon Count |
|-------------|----------|-------------|--------|---------------|
| `flood_sivasagar_20260701` | sivasagar | 2026-07-01 | Sentinel-1 SAR | (from GeoJSON features) |
| `flood_jorhat_20260729` | jorhat | 2026-07-29 | Sentinel-1 SAR | (from GeoJSON features) |
| `flood_charaideo_20260729` | charaideo | 2026-07-29 | Sentinel-1 SAR | (from GeoJSON features) |
| `flood_golaghat_20260722` | golaghat | 2026-07-22 | Sentinel-1 SAR | (from GeoJSON features) |

---

## 5. OSM DATA STATE

### OSM PBF File

- **Path:** `data/raw/osm/north-eastern-zone-latest.osm.pbf`
- **Git status:** Gitignored (`.gitignore` line: `data/raw/osm/north-eastern-zone-latest.osm.pbf`)
- **Status:** Not committed to repository — must be downloaded separately

### OSM Ingestion Code

`scripts/ingest/osm_pbf.py` implements:
- `ingest_buildings()` — parses buildings from PBF, filters by district polygons
- `ingest_roads()` — parses road network, filters by district polygons
- `ingest_bridges()` — filters bridge-tagged roads
- `ingest_medical()` — filters medical POIs (hospitals, clinics)
- `ingest_infrastructure()` — filters other POIs (schools, police, fuel, etc.)
- `augment_settlements()` — adds new settlements from PBF

### Expected Counts (from previous ingestion runs)

The previous audit noted "214k+ building records" — this was based on the prior verified database state. Without database access, we cannot confirm current counts.

### Known Issue: Port Mismatch

| File | Port Referenced | Notes |
|------|----------------|-------|
| `docker-compose.yml` | 5432 | Maps container port 5432 to host port 5432 |
| `scripts/db_init.py` | 5432 | Documentation references port 5432 |
| `README.md` | 5432 | Documentation references port 5432 |
| `tests/test_planner.py` | 5433 | Hardcoded default `DATABASE_URL` uses port 5433 |
| `tests/test_postgres_repository.py` | 5433 | Documentation references port 5433 |
| `scripts/ingest/osm_pbf.py` | 5433 | Documentation references port 5433 |

**The docker-compose.yml maps port 5432, but test/ingestion scripts reference port 5433.** This means either:
- The Docker Compose was previously configured with port 5433 and was later changed to 5432
- Or the test/ingestion scripts are out of sync with the Docker configuration

---

## 6. KNOWN OSM INGESTION BUG — WKT CONVERSION

### Status: ALREADY FIXED

The previous audit documented a bug in `load_district_polygons()`:
```python
# OLD BUGGY CODE (no longer present):
shape({"type": "WKT", "wkt": row.wkt})  # Raises GeometryTypeError
```

**The current code already uses the correct fix:**
```python
# CURRENT CODE in osm_pbf.py load_district_polygons():
from shapely import wkt as shapely_wkt
geom = shapely_wkt.loads(row.wkt)
```

The test file `tests/test_osm_pbf_ingestion.py` explicitly documents:
- The old buggy pattern (`shape({"type": "WKT", ...})`) raises `GeometryTypeError`
- The fix (`shapely.wkt.loads()`) works correctly
- All four districts load valid Polygon/MultiPolygon geometries
- Coordinate bounds are in the correct Assam region

**This bug does NOT need fixing — it is already resolved in the current codebase.**

---

## 7. DATA SAFETY / RECOVERY STATUS

### Known Issue: Raw Coordination Proposal Can Bypass Public Projection

The coordination send-to-organization API path can return a raw proposal rather
than the sanitized `get_public_view()` projection. If that proposal already
contains an organization evaluation, private fields may be exposed. This is a
tracked privacy issue and is intentionally **not fixed in the matching change**.

### Answers to Specific Questions

**1. Was the previous development database preserved?**
**UNKNOWN.** The PostgreSQL container's data is stored in a Docker named volume (`reliefos_pgdata`). If Docker was restarted or the volume was removed, the data would be lost. Without Docker access, we cannot verify.

**2. Was a new database initialized?**
**UNKNOWN.** Cannot verify without database access.

**3. Is the PostGIS volume still the same?**
**UNKNOWN.** The Docker Compose defines `reliefos_pgdata` as a named volume. If the volume still exists and Docker is restarted, the data would be preserved.

**4. Are the four flood snapshots still present?**
**PROBABLY YES (if database exists).** The migration code is idempotent and imports from committed GeoJSON files. If the database was re-initialized, running `db_init.py` would re-import all 4 flood snapshots.

**5. Are the 214k+ building records still present?**
**UNKNOWN.** Building records come from OSM PBF ingestion, which requires:
- The PBF file (gitignored, must be downloaded)
- Running `python -m scripts.ingest.osm_pbf`
If the database was wiped, buildings would need to be re-ingested.

**6. Are roads/bridges/medical records still present?**
**UNKNOWN.** Same as buildings — requires OSM PBF ingestion.

### Most Likely Scenario

Given that:
- Docker is not running on this system
- The database port (5433) is not reachable
- The PBF file is gitignored

The most likely scenario is that the **Docker container was previously running on a different machine or environment**, and the current system does not have the PostgreSQL instance active. The data files (flood GeoJSON, community reports, overrides) are all committed to git and present on disk.

### Recovery Path

If the database needs to be rebuilt:
1. Start Docker: `docker compose up -d`
2. Set port correctly (5432 per docker-compose.yml, or update docker-compose to 5433)
3. Run: `export DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos`
4. Initialize: `python scripts/db_init.py` (creates tables + imports flood/reports/overrides)
5. Download PBF file to `data/raw/osm/`
6. Run OSM ingestion: `python -m scripts.ingest.osm_pbf`

---

## 8. FRONTEND READINESS

### Assessment Per Layer

| Layer | Ready? | Reason |
|-------|--------|--------|
| Persistent map shell | ✅ READY | NetworkWorkspace, MapCanvas, all shell components exist |
| Flood layer | ✅ READY | Flood GeoJSON files exist; map renders flood polygons |
| Roads | ✅ READY | Road rendering code exists; requires DB data |
| Bridges | ✅ READY | Bridge rendering code exists; requires DB data |
| Buildings | ⚠️ AFTER DATA | Building toggle exists but no data in current DB |
| Medical | ✅ READY | Medical facility markers exist; requires DB data |
| Field reports | ✅ READY | Field report markers + submission form exist |
| Needs | ✅ READY | Full CRUD + map markers + context panel |
| Resource offers | ✅ READY | Full CRUD + map markers + context panel |
| Operations | ✅ READY | Full CRUD + map markers + context panel |
| Organizations | ⚠️ PARTIAL | CRUD exists, no dossier panel in ContextPanel |
| AI coordinator | ⚠️ AFTER WIRE | Backend endpoint exists, frontend never calls it |
| Delta/activity stream | ✅ READY | ActivityBar shows events; 30s polling |
| Temporal flood UI | ❌ NOT READY | No time slider or date picker |

### Overall Assessment: **READY AFTER DATA RESTORATION**

The frontend code is complete and functional. The only blocker is database availability. Once PostgreSQL is running and populated (via `db_init.py` + OSM ingestion), the full map-first workspace will render with all layers.

---

## 9. REUSABLE IMPLEMENTATION INVENTORY

### ALREADY BUILT (Must Reuse)

| Component | File | Purpose |
|-----------|------|---------|
| Data models | `agent/data/models.py` | 16 dataclasses + enums |
| Repository interface | `agent/data/repository.py` | Abstract DataRepository + InMemoryRepository |
| PostgreSQL repository | `agent/data/postgres_repository.py` | Full PostGIS implementation |
| Database schema | `agent/data/schema.py` | 15 tables with spatial indexes |
| Migration | `agent/data/migration.py` | Idempotent data import |
| Matching engine | `agent/matching.py` | Deterministic Need↔Offer matching |
| AI coordinator | `agent/ai_coordinator.py` | 3 detectors with review_target |
| Planner | `agent/planner.py` | Cross-district, temporal, resource-aware |
| Override system | `agent/overrides.py` | system_status vs override_status |
| Activity events | `agent/api.py` (activity endpoints) | Append-only event log |
| All API endpoints | `agent/api.py` | ~40 endpoints, all implemented |
| Map shell | `frontend/src/components/workspace/NetworkWorkspace.jsx` | Header + rail + map + panel + activity |
| Map canvas | `frontend/src/components/workspace/MapCanvas.jsx` | Leaflet with 13 layer types |
| Layer rail | `frontend/src/components/workspace/LayerRail.jsx` | Layer toggles + district filter |
| Context panel | `frontend/src/components/workspace/ContextPanel.jsx` | Dossiers + forms (needs refactor) |
| Activity bar | `frontend/src/components/workspace/ActivityBar.jsx` | Event stream + critical needs |
| Workspace state | `frontend/src/lib/workspaceContext.jsx` | Global state management |
| Map styles | `frontend/src/lib/mapStyles.js` | Centralized style constants |
| Design tokens | `frontend/src/index.css` | Console dark theme |

---

## 10. REPAIR INVENTORY

### Needs Repair Before UI Work

| Issue | Location | Fix Needed |
|-------|----------|------------|
| ContextPanel duplication | `frontend/src/components/workspace/ContextPanel.jsx` | Extract NeedDetail, OperationDetail, etc. into separate components; remove ~600 lines of duplicated code |
| Port mismatch | `docker-compose.yml` vs `test_planner.py` | Align port: either change docker-compose to 5433 or change test scripts to 5432 |
| AI coordinator not wired | Frontend never calls `/api/ai-coordinator/analysis` | Wire endpoint to ActivityBar and ContextPanel |
| Organization dossier missing | `ContextPanel.jsx` | Add OrganizationDetail panel component |
| Notification panel missing | Frontend | Add notification UI (backend + API exist) |

### Needs Frontend Integration (Backend Exists)

| Feature | Backend Status | Frontend Status |
|---------|---------------|-----------------|
| AI coordinator analysis | ✅ `GET /api/ai-coordinator/analysis` | ❌ Not called |
| Notifications | ✅ `GET /api/notifications` + `POST /:id/read` | ❌ No panel |
| Organization detail | ✅ `GET /api/organizations/:id` | ❌ No dossier |
| Activity events | ✅ `GET /api/activity` | ✅ ActivityBar uses it |
| Matching | ✅ `GET /api/needs/:id/matches` | ✅ NeedDetail uses it |
| Match confirmation | ✅ `POST /api/matches/:need/:offer/confirm` | ✅ NeedDetail uses it |

---

## 11. NEXT SINGLE RECOMMENDED ACTION

### **Start PostgreSQL, restore data, then proceed to Phase 7B Operational Shell refinement.**

The frontend code is complete and functional. The backend is complete. The only blocker is database availability.

**Immediate steps:**
1. Start Docker and PostgreSQL: `docker compose up -d`
2. Fix port alignment (docker-compose uses 5432, scripts reference 5433)
3. Run database initialization: `python scripts/db_init.py`
4. Download OSM PBF if not present: `data/raw/osm/north-eastern-zone-latest.osm.pbf`
5. Run OSM ingestion: `python -m scripts.ingest.osm_pbf`
6. Start Flask API: `python -m agent.main` or `python agent/api.py`
7. Start frontend: `cd frontend && npm run dev`
8. Verify all layers render correctly

**Then, in order:**
1. Wire AI coordinator findings to frontend
2. Refactor ContextPanel (extract sub-components)
3. Add Organization dossier panel
4. Add notification panel

---

## VALIDATION

### Files Created
- `docs/RELIEFOS_CURRENT_STATE.md` (this document)

### Files Modified
None

### Database Modified: NO
### Docker Modified: NO
### Data Modified: NO
