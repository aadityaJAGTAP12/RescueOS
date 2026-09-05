# Running ReliefOS — Complete System Guide

## Quick Start (Windows)

```bash
# Terminal 1: starts/reuses PostGIS, initializes persistent data, and runs Flask
cd RescueOS
start_backend.bat

# Terminal 2: React frontend dev server (port 3000)
cd RescueOS/frontend
npm run dev

# Terminal 3: (optional) Run tests or demo
cd RescueOS
python -m pytest -v          # run all 83 tests
python agent/main.py         # run the standalone demo
```

**That's it.** Ollama must be running for the LLM features (query parser, field intelligence extraction). The deterministic path (assessment, priority, allocation) works without Ollama.

The backend launcher is the required startup path on Windows. It anchors itself to the project directory, starts or reuses the PostGIS container, waits for PostgreSQL readiness, verifies the schema and persistent data, and only then starts the API. The database uses `localhost:5433`.

## URLs

| Service | URL | What it does |
|---|---|---|
| **Frontend** | http://localhost:3000 | Dashboard, query box, field intelligence page |
| **API** | http://localhost:5001 | All backend endpoints |
| **Ollama** | http://localhost:11434 | LLM inference (llama3.2) |

## Prerequisites

### Ollama (required for LLM features)

```bash
# Start Ollama (if not already running)
ollama serve

# Verify it's running
ollama list
# Should show: llama3.2:latest, mistral:latest
```

**What needs Ollama:**
- Query parser (POST /api/query) — parses free-text coordinator queries
- Field intelligence extraction (POST /api/field-intelligence) — extracts structured data from raw observations
- LLM synthesis (optional, when use_llm=True in assessment)

**What works WITHOUT Ollama:**
- Assessment (GET /api/assess) — deterministic flood/exposure/accessibility/priority
- Resource allocation — deterministic greedy allocator
- Location listing (GET /api/locations)
- Override system (POST /api/override, GET /api/override/status)
- Flood GeoJSON (GET /api/flood-geojson)
- All tests (python -m pytest)

## API Endpoints

### Core Assessment
```
GET  /api/locations                              → list of known locations
GET  /api/assess?location=<name>                 → full assessment for a named location
GET  /api/assess?lat=<lat>&lon=<lon>             → full assessment for coordinates
GET  /api/flood-geojson                          → raw flood polygon data for map
```

### Free-Text Query (Phase B)
```
POST /api/query
Body: {"query": "What's the priority status of Sivasagar Flood Zone?"}
→ parsed intent, resolved locations, assessments, allocation plan, capability gaps
```

### Field Intelligence
```
POST /api/field-intelligence
Body: {"raw_text": "Road blocked near the school. 30 people need water."}
→ extracted structured fields (people_count, needs, location, etc.)

GET  /api/field-intelligence/history
→ all submitted field intelligence reports
```

### Local Overrides
```
POST /api/override
Body: {"target_type": "facility", "target_id": "East Point Hospital", "new_status": "damaged", "reason": "..."}
→ override record

GET  /api/override/status?target_type=facility&target_id=...
→ current operational status with any active override

GET  /api/overrides
→ all active overrides
```

## Frontend Pages

| Page | URL | Description |
|---|---|---|
| Dashboard | http://localhost:3000/ | Main view: query box, location selector, map, evidence panel, priority assessment, data gaps |
| Field Intelligence | http://localhost:3000/field-intelligence | Submit and view raw field observations |

## Running Tests

```bash
# All 83 tests (no Ollama required)
python -m pytest -v

# Specific test files
python -m pytest tests/test_verification.py -v    # verification guardrails
python -m pytest tests/test_priority.py -v         # PDC scoring
python -m pytest tests/test_flood_tool.py -v       # flood detection
```

## What's NOT Included in Local Startup

### Kobo Webhook Receiver (separate app, port 5000)
The Kobo webhook receiver (`kobo_webhook_receiver.py`) is a **separate Flask app** that runs on port 5000. It's only needed if you're testing live KoboToolbox form submissions.

```bash
# Only if testing live Kobo submissions:
python kobo_webhook_receiver.py
```

This requires a **Cloudflare tunnel** (`cloudflared`) to expose port 5000 to the internet so KoboToolbox can reach it. For normal development/demo use, this is not needed.

### Cloudflare Tunnel (only for live Kobo testing)
```bash
# Only if testing live Kobo webhook:
cloudflared tunnel --url http://localhost:5000
```

## Troubleshooting

### "Ollama seems slow or unresponsive"
- Check nothing else is using it: `ollama list` should respond in <1s
- If llama3.2 is slow, try restarting: `ollama stop llama3.2 && ollama serve`
- The query parser adds ~8-12s latency for LLM parsing — this is normal for local inference

### "Frontend shows blank / can't connect to API"
- Confirm Flask API is running on port 5001: `curl http://localhost:5001/api/locations`
- The Vite dev server proxies `/api` to `localhost:5001` — both must be running

### "Cache miss / Overpass API errors"
- The system uses cached Overpass data in `data/cache/`. If cache files are missing, the tools will try the live Overpass API (may timeout).
- Cache files: `data/cache/accessibility_*.json`, `data/cache/buildings_*.json`, `data/cache/roads_*.json`

### "Tests fail with import errors"
- Run from the `RescueOS/` directory (not `RescueOS/agent/`)
- Ensure all dependencies are installed: `pip install -r requirements.txt`

### "Override not showing up"
- Overrides are stored in `data/overrides.json`
- The override system uses substring matching — "East Point Hospital" matches "East Point Hospital And Research Centre"
- Check: `curl http://localhost:5001/api/overrides`

## Architecture Summary

```
Frontend (React, port 3000)
    │
    ├── /api/* proxied to → Flask API (port 5001)
    │       │
    │       ├── Deterministic tools (flood, exposure, accessibility, allocation)
    │       │       └── Cache-first pattern (data/cache/)
    │       │
    │       ├── LLM tools (query parser, field intelligence)
    │       │       └── Ollama (llama3.2, port 11434)
    │       │
    │       └── Override system (data/overrides.json)
    │
    └── Direct page routes (/, /field-intelligence)

Kobo Webhook (separate, port 5000) — only for live form testing
    └── Requires Cloudflare tunnel for internet access
```
