# RescueOS

A multi-agent disaster-response framework that prioritizes rescue operations using real flood data, building exposure analysis, and medical facility accessibility scoring.

## Architecture

RescueOS uses a modular multi-agent architecture built on the [Strands SDK](https://github.com/strands-agents/sdk-python):

```
agent/
├── config.py                          # Model provider, constants, known locations
├── data_loader.py                     # Flood polygon loading, caching, distance helpers
├── main.py                            # Entry point (ranking + allocation demo)
│
├── tools/                             # Pure functions (testable, deterministic)
│   ├── flood_tool.py                  # Flood detection against Sentinel-1 GeoJSON
│   ├── accessibility_tool.py          # Medical facility proximity via Overpass API
│   ├── exposure_tool.py               # Building exposure counting within flood zones
│   └── allocation_tool.py             # Priority scoring (PDC), ranking, greedy allocation
│
└── agents/                            # Multi-agent reasoning components
    ├── flood_assessment_agent.py      # Flood + building exposure reasoning
    ├── accessibility_agent.py         # Medical accessibility reasoning
    ├── allocation_agent.py            # Priority computation reasoning
    └── coordinator_agent.py           # Top-level orchestration of all sub-agents
```

### Design Decisions

- **Model Provider Isolation**: All model-specific code lives in `config.py`. Switch from Ollama to AWS Bedrock by changing only that file.
- **Tool Composition over Agent.run()**: Strands Agent objects don't expose a `.run()` method for user code. Instead, agent tools call other `@tool` functions directly and compose results in Python — guaranteeing execution order with no step-skipping.
- **Cache-First Pattern**: Overpass API responses are cached locally in `data/cache/` to avoid rate limits and enable offline testing.
- **Honest Error Handling**: API timeouts and missing data are returned as explicit uncertainty states, not silent failures. Scoring treats unknown data conservatively.
- **v2 Recalibrated Scoring**: PDC score weights 35% building exposure, 35% flood-polygon scale, and 30% medical accessibility — adjusted after testing showed rural Upper Assam locations under-scored with the original formula.

## Running

```bash
# Main demo: rank 3 known locations + allocate resources
python agent/main.py

# Coordinator agent: multi-agent reasoning for a single location
python -c "from agent.agents.coordinator_agent import coordinator_agent_tool; coordinator_agent_tool('sivasagar_flood_zone')"
```

### Expected Output

```
#1: sivasagar_flood_zone — PDC 0.57 — PRIORITY
#2: sivasagar_settlement_flood — PDC 0.45 — EXPOSED
#3: sivasagar — PDC 0.1 — SAFE
```

## Tests

```bash
python -m pytest -v
```

## Data

Flood extent data comes from Earth Engine Sentinel-1 exports (`data/sivasagar_flood.geojson`). Building and medical facility data is fetched from the Overpass API and cached in `data/cache/`.

## Phases

- **Phase 1** (complete): Monolithic prototype → multi-agent architecture
- **Phase 2**: AWS Bedrock migration (update `config.py` only)
- **Phase 3**: Web UI, resource optimization solver, AWS service integrations
