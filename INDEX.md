ReliefOS Multi-Agent Architecture
==================================

INDEX OF DOCUMENTATION & FILES
================================

START HERE
==========

1. COMPLETION_SUMMARY.md
   → Executive summary of what was done
   → Validation results
   → How to run and what to expect
   → Next steps for hackathon

2. QUICK_REFERENCE.md
   → Developer's quick start guide
   → Running code examples
   → Testing and debugging
   → Extension points


FOR UNDERSTANDING THE CODE
===========================

3. agent/main.py
   → Entry point - read this first
   → Demonstrates ranking and allocation
   → Shows optional Coordinator demo

4. agent/config.py
   → Model provider configuration
   → Known locations
   → THE ONLY FILE TO CHANGE for Bedrock migration

5. agent/data_loader.py
   → FLOOD_POLYGONS initialization
   → Cache helpers (cache-first pattern)
   → Haversine distance function

Tools Layer:
6. agent/tools/flood_tool.py
   → get_flood_status() - flood detection
   
7. agent/tools/accessibility_tool.py
   → get_medical_accessibility() - medical facility location
   
8. agent/tools/exposure_tool.py
   → get_building_exposure() - building counting
   
9. agent/tools/allocation_tool.py
   → calculate_priority() - v2 recalibrated scoring
   → rank_locations() - orchestrate all tools
   → allocate_resources() - greedy allocation algorithm

Agents Layer:
10. agent/agents/flood_assessment_agent.py
    → Sub-agent for flood risk reasoning
    
11. agent/agents/accessibility_agent.py
    → Sub-agent for accessibility reasoning
    
12. agent/agents/allocation_agent.py
    → Sub-agent for priority computation
    
13. agent/agents/coordinator_agent.py
    → Top-level orchestration of all sub-agents
    → Demonstrates reliable step-by-step execution


FOR TECHNICAL DETAILS
=====================

14. RESTRUCTURING_REPORT.md
    → Complete technical overview
    → Design rationale
    → v2 scoring formula explanation
    → Migration checklist

15. VALIDATION_REPORT.md
    → Output verification against spike.py
    → Exact PDC scores and allocation
    → Error handling validation
    → Cache behavior confirmation

16. FOLDER_STRUCTURE.txt
    → Visual tree of all files
    → Layer organization
    → File purpose summary


REFERENCE MATERIALS
===================

17. spike.py
    → PRESERVED original single-file version
    → Can be run for direct comparison: python spike.py
    → Should produce identical output to agent/main.py

18. data/cache/ (directory)
    → 6 JSON files with cached Overpass API responses
    → Reused by restructured code
    → No cache invalidation needed
    

QUICK NAVIGATION BY TASK
========================

Want to...                          See...
──────────────────────────────────────────────────────
Run the code                        QUICK_REFERENCE.md (section: Running Code)
Understand the architecture         RESTRUCTURING_REPORT.md (section: Design)
Verify output is correct            VALIDATION_REPORT.md
Extend the system                   QUICK_REFERENCE.md (section: Extending)
Migrate to AWS Bedrock             RESTRUCTURING_REPORT.md (section: Migration)
Debug a problem                     QUICK_REFERENCE.md (section: Debugging Tips)
Understand v2 scoring              agent/tools/allocation_tool.py (comments)
See multi-agent reasoning           agent/agents/coordinator_agent.py
Test individual tools              QUICK_REFERENCE.md (section: Testing Logic)
Add a new location                  QUICK_REFERENCE.md (section: Extending)


FILE ORGANIZATION SUMMARY
=========================

agent/                          (Main package)
├── config.py                   (Bedrock migration point)
├── data_loader.py              (Data & caching)
├── main.py                     (Entry point)
├── tools/                      (Pure functions)
│   ├── flood_tool.py
│   ├── accessibility_tool.py
│   ├── exposure_tool.py
│   └── allocation_tool.py
└── agents/                     (Reasoning components)
    ├── flood_assessment_agent.py
    ├── accessibility_agent.py
    ├── allocation_agent.py
    └── coordinator_agent.py


LAYER STRUCTURE
===============

Layer 1: Configuration
  ├── config.py (model provider, constants)
  └── data_loader.py (initialization, caching)

Layer 2: Tools (Data Gathering)
  ├── flood_tool.py
  ├── accessibility_tool.py
  ├── exposure_tool.py
  └── allocation_tool.py

Layer 3: Agents (Reasoning)
  ├── flood_assessment_agent.py
  ├── accessibility_agent.py
  ├── allocation_agent.py
  └── coordinator_agent.py (orchestration)

Layer 4: Application
  └── main.py (entry point)


KEY METRICS
===========

✓ Files Created:         16 Python modules
✓ Lines Reorganized:     600+ → modularized
✓ Model Isolation:       config.py (1 file to change)
✓ Output Validation:     100% match with spike.py
✓ PDC Scores:           0.57, 0.45, 0.1 (identical)
✓ Test Locations:       3 (sivasagar, sivasagar_flood_zone, sivasagar_settlement_flood)
✓ Cache Files:          6 (preserved, no invalidation)
✓ Error Handling:       Preserved (timeout, API errors, data gaps)
✓ Scoring Formula:      v2 recalibrated (unchanged)
✓ Multi-Agent Steps:    4 (flood → accessibility → priority → synthesis)


EXECUTION FLOW
==============

Command: python agent/main.py

Step 1: Load Configuration
  ├── Import config.py (model, KNOWN_LOCATIONS)
  └── Import data_loader.py (FLOOD_POLYGONS)

Step 2: Rank Locations
  ├── For each location, call 3 tools:
  │   ├── get_flood_status()
  │   ├── get_building_exposure()
  │   └── get_medical_accessibility()
  ├── Compute priority score
  └── Sort by PDC score (descending)

Step 3: Display Rankings
  └── Print sorted results

Step 4: Allocate Resources
  ├── Start with available resources
  ├── For each location (highest priority first):
  │   └── Allocate until resource exhausted
  └── Print allocation plan

Step 5: Optional - Run Coordinator Demo
  ├── Call coordinator_agent_tool()
  ├── Orchestrate sub-agents (flood → accessibility → priority)
  └── Synthesize comprehensive assessment


RUNNING TESTS
=============

Basic Test (Ranking):
  cd d:\RescueOS\RescueOS
  python agent\main.py
  
  Expected: 3 locations ranked by PDC score
  Time: ~5 seconds (cache hits)

Multi-Agent Test (Coordinator):
  python -c "from agent.agents.coordinator_agent import coordinator_agent_tool; coordinator_agent_tool('sivasagar_flood_zone')"
  
  Expected: Step-by-step reasoning with final recommendation
  Time: ~10 seconds

Comparison Test (vs spike.py):
  python agent\main.py > new_output.txt
  python spike.py > old_output.txt
  # Compare outputs (should be identical except for timing/spacing)


API OVERVIEW
============

Configuration:
  from agent.config import KNOWN_LOCATIONS, model, OVERPASS_URL

Data Loading:
  from agent.data_loader import FLOOD_POLYGONS, haversine_km

Tools:
  from agent.tools.flood_tool import get_flood_status
  from agent.tools.accessibility_tool import get_medical_accessibility
  from agent.tools.exposure_tool import get_building_exposure
  from agent.tools.allocation_tool import calculate_priority, rank_locations, allocate_resources

Agents:
  from agent.agents.flood_assessment_agent import flood_assessment_agent_tool
  from agent.agents.accessibility_agent import accessibility_agent_tool
  from agent.agents.allocation_agent import allocation_agent_tool
  from agent.agents.coordinator_agent import coordinator_agent_tool


TROUBLESHOOTING
===============

Problem: ModuleNotFoundError: No module named 'agent'
Solution: Run from d:\RescueOS\RescueOS/ directory (where agent/ folder is)

Problem: Ollama connection error
Solution: Ensure Ollama is running on http://localhost:11434
  or update agent/config.py with correct Ollama host

Problem: Overpass API timeout
Solution: Already handled by code (returns "UNAVAILABLE")
  Check data/cache/ folder for cached files
  Delete .json files to force fresh query

Problem: Output doesn't match spike.py
Solution: Check cache file timestamps
  Delete data/cache/*.json and rerun
  Verify KNOWN_LOCATIONS hasn't changed


SUCCESS INDICATORS
==================

✓ Restructuring successful if:
  ├── python agent/main.py runs without errors
  ├── Output shows 3 ranked locations
  ├── PDC scores are 0.57, 0.45, 0.1
  ├── Resource allocation shows correct distribution
  └── All cache files load successfully [CACHE HIT]

✓ Coordinator reliable if:
  ├── coordinator_agent_tool runs without errors
  ├── All 4 steps execute (flood → accessibility → priority → synthesis)
  ├── Final recommendation cites specific numerical evidence
  └── No step skipping or missing tool calls


NEXT PHASES
===========

Phase 1 (Current): ✓ COMPLETE
  Restructure spike.py into multi-agent architecture
  Validate output matches exactly
  Document design and rationale

Phase 2: Bedrock Migration
  Update agent/config.py with AWS Bedrock client
  Rerun tests to confirm identical output
  Deploy to AWS infrastructure

Phase 3: Enhancement
  Improve Coordinator reasoning for user-facing responses
  Add resource optimization solver
  Integrate with AWS services (CloudWatch, S3, Lambda)

Phase 4: Production Deployment
  Web UI for disaster response assessment
  Real-time monitoring and alerts
  Integration with humanitarian organizations


MAINTENANCE NOTES
=================

For Future Developers:

1. Before modifying scoring logic:
   - Run baseline: python agent/main.py > baseline.txt
   - Make changes in agent/tools/allocation_tool.py
   - Run comparison: python agent/main.py > new.txt
   - Verify changes are intentional

2. Before adding new tools:
   - Create in agent/tools/{name}_tool.py
   - Decorate with @tool
   - Test independently
   - Integrate into agent as needed

3. Before migrating to Bedrock:
   - Update agent/config.py only
   - No other files should change
   - Rerun full test suite
   - Compare with spike.py output

4. For caching issues:
   - Clear: rm data/cache/*.json
   - Check: ls -la data/cache/
   - Verify: timestamps should be recent


CONTACT & SUPPORT
=================

This is documentation for the ReliefOS hackathon project.
All code is self-contained in d:\RescueOS\RescueOS/agent/

For questions about:
- Architecture design      → See RESTRUCTURING_REPORT.md
- Running the code        → See QUICK_REFERENCE.md
- Output validation       → See VALIDATION_REPORT.md
- AWS Bedrock migration   → See agent/config.py + RESTRUCTURING_REPORT.md

---

Last Updated: 2026-08-20
Status: Complete & Validated ✓
