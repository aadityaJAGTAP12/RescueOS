# ReliefOS

ReliefOS is a generalized disaster-response coordination and operational intelligence platform that turns fragmented spatial, field, organizational, and operational information into explainable coordination workflows with human-controlled actions.

ReliefOS is generalized at the orchestration layer and validated through an Assam flood case study.

## Problem

During flood and disaster response, the information needed to act is scattered across incompatible places: satellite flood extents, road/bridge conditions, field observations phrased in free text, and the private inventories of many separate organizations. No single operational picture exists, so coordination gaps (unmet needs), duplicated effort, and unsafe routing decisions are discovered late — or not at all.

## Solution

ReliefOS builds a shared operational picture on PostgreSQL + PostGIS and runs an event-driven multi-agent runtime over it:

- **A Network Main Agent** reasons over shared state with eight specialist workers (situation, exposure, medical, logistics, access, field, coordination, evidence).
- **Organization (NGO) Main Agents** reason over each organization's private state plus the shared picture, with private specialist workers (inventory, team, mission, logistics, field).
- **Bounded Strands-based reasoning** turns messy natural language into structured, verified operational data and interprets deterministic findings.
- **A human-approval boundary** ensures every consequential action — publishing an offer, confirming a match, creating an operation — is explicitly approved by a person.
- **A proactive intelligence runtime** continuously scans for coordination gaps, access risks, medical/logistics gaps, exposure risk, and conflicting field reports, and reconciles finding lifecycles over time.

## Who It Is For

- **Emergency operations coordinators** who need one map-first picture of hazards, access, needs, and response activity.
- **Relief organizations (NGOs)** that must decide what to offer without exposing private inventory, teams, or missions.
- **Field personnel and communities** who report conditions in plain language and need those reports to become structured, verified operational data.

## Why It Is Different

- **Geographic issues:** like an issue tracker for the physical world — every need lives inside a hazard/access/medical context, not just a list.
- **Privacy as architecture:** organizations keep private state; only explicitly approved contributions cross the boundary. This is enforced structurally (public-view projections), not by convention.
- **Deterministic control loop with bounded AI:** deterministic agents compute, rank, and detect; LLM reasoning is bounded, evidence-cited, and guarded (fabricated numbers are detected and discarded). The deterministic path keeps working when the LLM is unavailable.
- **Explainability:** every finding carries provenance (OBSERVED / DERIVED / USER_PROVIDED / ASSUMED / SYNTHETIC / UNKNOWN), evidence, uncertainty, and data gaps.
- **Human-in-the-loop by design:** agents detect, calculate, rank, summarize, interpret, explain, recommend, and propose — they do not autonomously take consequential actions.

## Core Workflow

```text
Need
→ Assessment
→ Coordination
→ Proposal
→ Organization Evaluation
→ Human Approval
→ Offer / Operation
```

Concretely: a need is created from field data or coordinator input → the Network Main Agent analyzes it → a coordination proposal is generated for a suitable organization → the organization's NGO Main Agent evaluates it against private state (inventory, teams, missions) → a human approves publication → a public resource offer and operation are created on the shared state. The lifecycle is `PROPOSED → PENDING_ORG_REVIEW → ORG_RECOMMENDED → PENDING_HUMAN_APPROVAL → PUBLISHED → CONFIRMED` (or `DECLINED`/`EXPIRED`).

## Architecture

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the architecture diagram and its explanation.

## AI Agent Architecture

```text
Network Main Agent                      Organization Main Agent (per org)
  ├ Situation Worker                     ├ Inventory Worker
  ├ Exposure Worker                      ├ Team Worker
  ├ Medical Worker                       ├ Mission Worker
  ├ Logistics Worker                     ├ Logistics Worker
  ├ Access Worker                        └ Field Worker
  ├ Field Worker                             │
  ├ Coordination Worker                 PRIVATE ORG STATE
  └ Evidence Worker                          │
       │                                public contribution
       ▼                                     │
SHARED OPERATIONAL STATE                HUMAN APPROVAL
(PostgreSQL + PostGIS)                       │
                                        OFFER / OPERATION
```

- The **Network Main Agent** never reads organization-private state. Events are routed deterministically to relevant specialists; failures are isolated as explicit data gaps rather than fabricated findings.
- **Organization Main Agents** combine `PrivateOrganizationContext` with `SharedNetworkContext`. Their recommendations include a proposed publication — which stays a proposal until a human approves it.
- There is no uncontrolled peer-to-peer agent chatter: `Worker → Main Agent → shared operational object → other Main Agent`.

## Strands Agents Integration

[Strands Agents](https://github.com/strands-agents/sdk-python) (`strands-agents==1.52.0`) provides the **bounded reasoning layer** inside ReliefOS:

| Strands component | Location | Role |
|---|---|---|
| Query parsing agent | `agent/tools/query_parser_tool.py` | Extracts structured intent from free-text coordinator queries; never answers the query itself |
| Field intelligence extraction agent | `agent/tools/field_intelligence_tool.py` | Extracts structured fields (needs, people counts, road/facility statuses) from raw field observations |
| Coordinator agent | `agent/agents/coordinator_agent.py` | Evidence-based LLM synthesis over pre-gathered deterministic evidence |
| Specialist agent tools | `agent/agents/flood_assessment_agent.py`, `accessibility_agent.py`, `supply_matching_agent.py` | Strands `@tool` specialists invoked by the coordinator agent |
| Bounded need/offer judgment | `agent/reasoning/need_offer_judgment.py` | 2-second-timeout advisory interpretation of deterministic match facts, with ungrounded-number rejection |
| Deterministic `@tool` functions | `agent/tools/flood_tool.py`, `exposure_tool.py`, `accessibility_tool.py`, `allocation_tool.py`, `road_status_tool.py`, `region_scan_tool.py` | Deterministic operations exposed in Strands tool format |

Model provider: `strands.models.ollama.OllamaModel` configured in `agent/config.py` (local Ollama, isolated so it can be swapped for another provider in one file).

ReliefOS's deterministic event-driven operational runtime — agent contracts (`AgentFinding`, provenance, severity), `AgentEvent`, deterministic event routing, the transactional outbox, persistence, privacy boundaries, human-in-the-loop gates, and the Network/NGO main-agent orchestration — is **custom application architecture**, built around Strands rather than on top of it.

> Strands provides the bounded reasoning layer inside a deterministic, event-driven operational agent architecture.

## Human-in-the-Loop

Agents can detect, calculate, rank, summarize, interpret, explain, recommend, and **propose**. Consequential actions — publishing a resource offer, confirming a need/offer match, creating or changing an operation, applying an override — require explicit human approval through the API, and approvals are recorded in the audit log. There is no code path in which an agent autonomously publishes, commits, or mutates shared operational state.

## Privacy / Multi-Organization Model

- The **network** sees shared/public operational state: needs, published offers, operations, organizations, field reports, overrides.
- **Organizations** retain private state: resources, teams, missions. The Network Main Agent structurally cannot read it.
- Coordination proposals carry a public view (`get_public_view`) that excludes private evaluation factors; only fields explicitly approved for publication are converted into a public offer (`agent/coordination/publication.py`).
- Organization-scoped endpoints resolve the organization server-side per request (`agent/org_context.py`); client-supplied organization IDs are not trusted.

## Event-Driven Runtime

- **Transactional outbox:** `AgentEvent` records are persisted (PostgreSQL) with a full lifecycle (`PENDING → CLAIMED → PROCESSING → PROCESSED / FAILED / SKIPPED_DUPLICATE`), retry counts, and error payloads.
- **Deterministic routing:** a static routing table maps event types to the specialist domains that should process them — no LLM in the control loop.
- **Idempotency:** duplicate events are detected and skipped; replays are supported for observability (`POST /api/agent/events/<event_id>/replay`).
- **Stale recovery:** events stuck in CLAIMED/PROCESSING are requeued (or failed after retry exhaustion) by a background recovery loop.
- **Failure isolation:** a failing specialist produces an explicit data-gap finding; it never crashes the pipeline or fabricates a result.

## Proactive Intelligence

The proactive runtime (`agent/proactive/runtime.py`) periodically scans operational state with deterministic detectors, deduplicates advisory notifications, and reconciles finding lifecycles (`NEW → ACTIVE → RESOLVED`):

| Detector | Purpose |
|---|---|
| `coordination_gap` | Needs with no responder beyond an age threshold; duplicate responses |
| `access_risk` | Road/bridge overrides affecting access |
| `exposure_risk` | Populations/buildings inside or near flood extents |
| `medical_gap` | Medical accessibility gaps |
| `logistics_gap` | Unmatched resource needs vs published offers |
| `field_conflict` | Contradictory field reports about the same target |

All findings are advisory: they carry evidence, uncertainty, data gaps, and a review target for a human.

## Geospatial Operational Layer

Operational state persists in **PostgreSQL 16 + PostGIS 3.4** (15 tables: districts, settlements, flood_snapshots, field_reports, overrides, buildings, medical_facilities, roads, organizations, needs, resource_offers, operations, operation_participants, activity_events, notifications — plus agent_events, coordination_proposals, users, organization_memberships, audit_logs). Spatial filtering (point-in-polygon, intersects, radius) executes database-side via GiST-indexed geometries (SQLAlchemy Core + GeoAlchemy2). A repository abstraction falls back to in-memory storage for development and tests; production startup refuses to run without a durable PostgreSQL `DATABASE_URL`.

## Data / Case Study

Current validation uses **Assam flood data** (Sentinel-1 SAR-derived flood polygons for Sivasagar, Jorhat, Charaideo, Golaghat — July 2026) plus OpenStreetMap infrastructure (ODbL — see attribution in data caches), served through a repository layer that is district-agnostic: no district-specific branching exists in the runtime, and generalization is enforced by tests. Google Earth Engine export scripts (`agent/gee/`) document how flood snapshots were produced.

- **Current validation:** Assam flood / geospatial operational data
- **Architecture:** generalized disaster-response orchestration
- **Future:** live multi-source disaster ingestion adapters (not implemented)

## Security

- **Authentication:** session-based auth with HMAC-SHA256-signed tokens (`/api/auth/*`); fail-closed enforcement in production (`AUTH_ENFORCED=true`).
- **Authorization:** organization-scoped access control with server-side org resolution; production configuration validation fails fast on insecure settings (`agent/config.py` → `validate_production_readiness`).
- **Privacy boundaries:** public-view projections for all network-facing routes (see above).
- **Audit logging:** immutable audit records for consequential mutations and approvals (`agent/audit/`).
- **Observability:** request correlation IDs (`X-Request-ID`), latency measurement, structured access logs (`agent/middleware/observability.py`).
- **Security headers & error masking:** defensive HTTP headers and generic production errors (`agent/middleware/security.py`); secrets are never logged.

## Running Locally

Prerequisites: Python 3.11+, Docker (for PostgreSQL), Node.js (for the frontend). Ollama is **optional** — needed only for LLM features (query parsing, field intelligence extraction, LLM synthesis); the deterministic path runs without it.

```bash
# 1. Install backend dependencies
pip install -r requirements.txt

# 2. Start PostgreSQL + PostGIS and run the API (Windows)
start_backend.bat
#    …or manually:
docker compose up -d
export DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos
python scripts/db_init.py        # creates schema + imports district/flood/field data
python -m agent.api              # Flask API on http://localhost:5001
```

```bash
# 3. Frontend (separate terminal)
cd frontend
npm install
npm run dev                      # http://localhost:3000 (proxies /api to :5001)
```

Optional services:

```bash
ollama serve                     # LLM features (llama3.2) — optional
cd osrm && ./setup.sh            # local OSRM routing server — optional (haversine fallback used otherwise)
python kobo_webhook_receiver.py  # KoboToolbox webhook receiver (port 5000) — optional
```

Production-like startup (validates config, requires durable PostgreSQL, starts the outbox worker + proactive scheduler): `python -m agent.prod_startup`. See `.env.example` for all environment variables and `BACKUP_AND_RECOVERY.md` for backup/restore procedures.

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API | http://localhost:5001 |
| PostgreSQL + PostGIS | localhost:5433 |
| Ollama (optional) | http://localhost:11434 |

## Testing

```bash
# Full backend suite (in-memory mode — no services required)
RELIEFOS_MEMORY=1 python -m pytest tests/ -v

# PostgreSQL integration tests (requires DATABASE_URL)
export DATABASE_URL=postgresql://reliefos:reliefos@localhost:5433/reliefos
python -m pytest tests/ -v

# Frontend
cd frontend && npm test
```

Verified results:

```text
Backend (PostgreSQL):  736 passed / 0 skipped / 0 failed
Backend (memory mode): 692 passed / 20 skipped / 0 failed   (skips are DB-required tests)
Frontend:               47 passed / 0 failed
```

## Project Structure

```text
agent/                    Backend: API, agents, tools, data layer, runtime
  agents/                 Network/NGO main agents, workers, events, event router
  tools/                  Deterministic tools + Strands LLM extraction tools
  data/                   Models, repository abstraction, PostgreSQL repository, schema
  coordination/           Proposal lifecycle, publication, candidate selection
  proactive/              Proactive runtime, scheduler, deterministic detectors
  reasoning/              Bounded LLM judgment with verification guardrails
  auth/ audit/ middleware/  Security, audit logging, observability
  gee/                    Google Earth Engine flood export pipeline (case-study data)
frontend/                 React 19 + Vite + Tailwind + Leaflet workspace UI
  src/components/workspace/  Map-first console: map canvas, layer rail, context panel, activity bar
tests/                    38 backend test modules + frontend unit tests (frontend/src/__tests__)
scripts/                  DB init, ingestion, seeding, backup verification
docs/                     Architecture, audits, phase documentation
osrm/                     Local OSRM routing server setup
data/                     Flood GeoJSON, caches, org fixtures, migration sources
```

## Configuration

Copy `.env.example` to `.env` and set values. Key variables (all documented with production requirements in `.env.example`):

| Variable | Purpose |
|---|---|
| `ENVIRONMENT` | `development` \| `production` — gates fail-closed behavior |
| `DATABASE_URL` | PostgreSQL + PostGIS connection string (required in production) |
| `RELIEFOS_SECRET_KEY` | Session-token signing secret (≥32 random chars, required in production) |
| `AUTH_ENFORCED` | `true` rejects unauthenticated requests (required in production) |
| `CORS_ALLOWED_ORIGINS` | Trusted frontend origins |
| `EVENT_WORKER_*` | Outbox worker: enable, poll interval, batch size |
| `PROACTIVE_*` | Proactive scheduler: enable, scan interval |
| `HOST`, `PORT`, `LOG_LEVEL` | Server binding and logging |

Never commit real `.env` values. No secrets or credentials are stored in this repository.

## Open Source License

This project is licensed under the **Apache License 2.0** — see [LICENSE](LICENSE).

Third-party data and services used: OpenStreetMap data (ODbL attribution retained in data caches), Sentinel-1-derived flood polygons (case-study data), Overpass API, OSRM, Ollama, Strands Agents, Flask, SQLAlchemy/GeoAlchemy2. See `.env.example` and `docs/` for integration details.

## Roadmap

Future work (not implemented in this repository):

- Live multi-source disaster ingestion adapters
- Additional disaster types beyond flooding
- AWS deployment (ECR/ECS/Fargate, RDS for PostgreSQL/PostGIS, Secrets Manager)
- Production-scale runtime hardening and stronger distributed scheduling
- Additional operational integrations (real-time field confirmation, live river gauges)

## Hackathon / Demo

The submission demo walks the end-to-end workflow: create a need from field data → the Network Main Agent analyzes it and detects a coordination gap → a coordination proposal is sent to an organization → the NGO Main Agent evaluates it against private inventory/teams → a human approves publication → the public offer and operation appear on the shared map — all with evidence, provenance, and auditability visible at each step. Bounded Strands reasoning is demonstrated through free-text query parsing and field-intelligence extraction.
