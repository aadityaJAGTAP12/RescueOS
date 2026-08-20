Quick Reference - ReliefOS Multi-Agent Architecture
====================================================

RUNNING THE CODE
================

1. Run Main Demo (ranking + allocation):
   cd d:\RescueOS\RescueOS
   python agent\main.py

2. Run Coordinator Agent (multi-agent reasoning):
   python -c "from agent.agents.coordinator_agent import coordinator_agent_tool; coordinator_agent_tool('sivasagar_flood_zone')"

3. Run Original Reference:
   python spike.py


KEY FILES BY PURPOSE
====================

Setup & Configuration:
  agent/config.py              — Model provider, constants, known locations
  agent/data_loader.py         — FLOOD_POLYGONS, cache infrastructure

Tools (Pure Functions):
  agent/tools/flood_tool.py           — Flood detection
  agent/tools/accessibility_tool.py   — Medical facility access
  agent/tools/exposure_tool.py        — Building exposure counting
  agent/tools/allocation_tool.py      — Priority scoring + ranking + allocation

Agents (Reasoning Components):
  agent/agents/flood_assessment_agent.py       — Flood risk reasoning
  agent/agents/accessibility_agent.py          — Access barrier reasoning
  agent/agents/allocation_agent.py             — Priority computation reasoning
  agent/agents/coordinator_agent.py            — Top-level orchestration

Entry Points:
  agent/main.py                — Demo script


CORE CONCEPTS
=============

1. Tools = Pure Functions
   get_flood_status(location) → dict
   get_medical_accessibility(location) → dict
   get_building_exposure(location) → dict
   calculate_priority(...) → dict
   
   → Deterministic, cacheable, testable
   → Decorated with @tool for Strands framework

2. Agents = Reasoning Components
   Each agent: Strands Agent with specific tools + system prompt
   → Internal reasoning about specific concern
   → Exposed as @tool for higher-level orchestration
   
   flood_assessment_agent_tool(location) → assessment text
   accessibility_agent_tool(location) → assessment text
   allocation_agent_tool(...) → priority explanation

3. Coordinator = Orchestration
   Calls sub-agents in sequence: flood → accessibility → priority
   Extracts data from each step before calling next
   → No step-skipping
   → No data transcription errors
   → Explicit uncertainty handling


DATA FLOW
=========

Input: location name (string)

Step 1: Flood Assessment Agent
  ├─ get_flood_status(location)
  │  └─ {flooded, total_polygons, nearest_polygon_km2, detail}
  └─ get_building_exposure(location)
     └─ {total_buildings, exposed_count, exposure_ratio, detail}

Step 2: Accessibility Agent
  └─ get_medical_accessibility(location)
     └─ {medical_distance_km, medical_facility_name, detail, data_available}

Step 3: Allocation Agent
  └─ calculate_priority(flood_detected, exposure_ratio, ...)
     └─ {pdc_score, category, recommendation}

Step 4: Coordinator Synthesis
  └─ Combines all findings into comprehensive assessment


PRIORITY SCORING FORMULA (v2 Recalibrated)
===========================================

exposure_score = min(exposure_ratio * 6.0, 1.0)
flood_scale_score = min(nearest_flood_polygon_km2 / 5.0, 1.0)

accessibility_score = 
  0.5      if medical_distance_km < 0 (unknown)
  1.0      if medical_distance_km > 15
  0.66     if 5 < medical_distance_km <= 15
  0.33     if 0 <= medical_distance_km <= 5

pdc_score = (exposure_score * 0.35) + 
            (flood_scale_score * 0.35) + 
            (accessibility_score * 0.30)

Categories:
  PDC >= 0.75   →  HIGH PRIORITY
  0.5 <= PDC < 0.75  →  PRIORITY
  0.25 <= PDC < 0.5  →  EXPOSED
  PDC < 0.25    →  SAFE

Why v2 Recalibrated?
  Rural flood zones (Upper Assam) have low building density
  → Farmland/rivers dominant, not settlements
  Original scoring weighted buildings too heavily
  → Under-scored large flood areas with sparse development
  Fix: Equal weight to flood polygon size + building exposure


TESTING LOGIC
=============

Unit Testing (individual tools):
  from agent.tools.flood_tool import get_flood_status
  result = get_flood_status("sivasagar")
  assert result['flooded'] == True

Integration Testing (ranking):
  from agent.tools.allocation_tool import rank_locations
  ranked = rank_locations(['sivasagar', 'sivasagar_flood_zone'])
  assert ranked[0]['location'] == 'sivasagar_flood_zone'
  assert ranked[0]['pdc_score'] > ranked[1]['pdc_score']

Validation Testing (vs spike.py):
  # Run both and compare PDC scores and allocation
  python agent/main.py  # Check output
  python spike.py       # Compare output
  # Both should be identical


CACHE MANAGEMENT
================

Cache Location: data/cache/

Cache Files (by query type and location):
  {query_type}_{location}.json
  
  Examples:
    buildings_sivasagar.json
    accessibility_sivasagar_flood_zone.json

Cache Behavior:
  1. Check if file exists locally
  2. If cache hit → load and use
  3. If cache miss → query Overpass API
  4. Save API response to cache for future runs

Cache Invalidation:
  Delete individual .json files to force fresh API query
  Cache is automatically regenerated on next run

Production Note:
  In Bedrock migration, consider cloud-based caching (S3 or similar)


MIGRATION TO AWS BEDROCK
========================

Step 1: Identify isolation point
  ✓ All model-provider code is in agent/config.py

Step 2: Update config.py
  Replace:
    from strands.models.ollama import OllamaModel
    model = OllamaModel(host="http://localhost:11434", model_id="llama3.2")
  
  With:
    import boto3
    # AWS Bedrock client setup
    model = BedrockModel(region="us-east-1", model_id="...")

Step 3: No other changes needed!
  All tools, agents, and main.py continue to work unchanged
  Strands framework will handle model provider abstraction

Step 4: Test
  python agent/main.py  # Should produce same output


EXTENDING THE SYSTEM
====================

Adding a New Tool:

  1. Create: agent/tools/new_tool.py
     from strands import tool
     
     @tool
     def get_something(location: str) -> dict:
         # Implementation
         return {...}

  2. Create agent to use it: agent/agents/something_agent.py
     Similar pattern to existing agents

  3. Add to Coordinator: agent/agents/coordinator_agent.py
     Call something_agent_tool() in appropriate step

  4. Update main.py if needed for demos

Adding a New Location:

  1. Update: agent/config.py
     KNOWN_LOCATIONS = {
         "new_location": (lon, lat),
         ...
     }
  
  2. Run: python agent/main.py
     Will automatically assess new location

Modifying Scoring:

  1. Edit: agent/tools/allocation_tool.py
     Modify calculate_priority() weights and thresholds
  
  2. Test: python agent/main.py
     Verify output still makes sense
     (or compare with spike.py if changing intentionally)


DEBUGGING TIPS
==============

Enable Debug Output:
  Tools print [Tool: name] and [CACHE HIT/MISS] messages
  Agents print [AGENT: name] messages
  Coordinator prints step-by-step execution

Check Cache:
  ls -la data/cache/
  File timestamps show when data was cached
  Delete to force fresh API query

API Errors:
  Tools return error dict with data_available=False
  Check "error" field for details
  Scoring continues with fallback values

Verify Ranking:
  Print PDC scores to confirm correct ordering
  Check category assignments (NONE, SAFE, EXPOSED, PRIORITY, HIGH PRIORITY)

Performance Profiling:
  Add timing around tool calls:
    import time
    start = time.time()
    result = get_flood_status(loc)
    print(f"Flood status took {time.time() - start:.2f}s")


ARCHITECTURE PHILOSOPHY
========================

1. Separation of Concerns
   Tools → data gathering
   Agents → reasoning about data
   Coordinator → orchestration
   Config → environment configuration

2. Deterministic Data Flow
   Each tool returns structured dict
   Each agent processes specific concern
   No data loss or transformation errors
   Explicit error states (not silent failures)

3. Caching & Optimization
   Cache-first pattern reduces API load
   Deterministic outputs enable offline testing
   Real data for 3 known locations already cached

4. Model Provider Independence
   All model code centralized in config.py
   Agents use abstract Strands interface
   Switch providers by updating one file

5. Multi-Agent via Tool Composition
   Sub-agents are tools for Coordinator
   Step-by-step orchestration (not LLM chaining)
   Guarantees reliable execution order
   Avoids step-skipping and hallucinations


USEFUL COMMANDS
===============

# Run full demo
cd d:\RescueOS\RescueOS && python agent\main.py

# Test Coordinator for one location
python -c "from agent.agents.coordinator_agent import coordinator_agent_tool; print(coordinator_agent_tool('sivasagar_flood_zone'))"

# Compare with spike.py
python spike.py > output_old.txt
python agent\main.py > output_new.txt
diff output_old.txt output_new.txt

# List cached files
dir data\cache\

# Clear all cache
del data\cache\*.json

# Profile a single tool
python -c "from agent.tools.flood_tool import get_flood_status; print(get_flood_status('sivasagar'))"

# Check what locations are available
python -c "from agent.config import KNOWN_LOCATIONS; print(list(KNOWN_LOCATIONS.keys()))"

---

For detailed technical documentation, see:
  RESTRUCTURING_REPORT.md  - Full migration summary
  VALIDATION_REPORT.md     - Output verification
  FOLDER_STRUCTURE.txt     - File organization
