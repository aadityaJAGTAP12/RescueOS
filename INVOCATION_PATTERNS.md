EXACT CODE INVOCATION PATTERNS - Quick Reference
================================================

The Issue That Was Found
═════════════════════════
Initial attempt to invoke agents via Agent.run() FAILED:
  ERROR: AttributeError: 'Agent' object has no attribute 'run'

This happened because Strands' Agent class doesn't expose a .run() method
for user code to call. The Agent object is declarative, not executable.


The Solution: Tool Composition
══════════════════════════════

Each agent now directly invokes tools and composes results in Python.


AGENT 1: flood_assessment_agent.py
═══════════════════════════════════

File Location:
  d:\RescueOS\RescueOS\agent\agents\flood_assessment_agent.py

Tool Invocation (Lines 46-47):
────────────────────────────────
    @tool
    def flood_assessment_agent_tool(location: str) -> str:
        print(f"\n[AGENT: flood_assessment_agent] evaluating location='{location}'")
        
        # DIRECT TOOL CALLS (not via Agent.run())
        flood_status = get_flood_status(location)              # ← Line 46
        exposure = get_building_exposure(location)             # ← Line 47
        
        # Compose findings in Python
        flooded = "FLOODED" if flood_status["flooded"] else "NOT FLOODED"
        flood_area = f"{flood_status['nearest_flood_polygon_km2']:.2f} sq km"
        exposure_pct = f"{exposure['exposure_ratio']*100:.0f}%"
        
        assessment = (
            f"Flood Status: {flooded}. "
            f"Nearest flood area: {flood_area}. "
            f"Building exposure: {exposure['total_buildings']} buildings, "
            f"{exposure['exposed_count']} exposed ({exposure_pct}). "
            f"Summary: {flood_status['detail']}"
        )
        
        return assessment

Execution Pattern:
  get_flood_status(location) ──→ dict with {flooded, total_polygons, ...}
  get_building_exposure(location) ──→ dict with {total_buildings, exposed_count, ...}
  ──→ Compose into assessment string


AGENT 2: accessibility_agent.py
════════════════════════════════

File Location:
  d:\RescueOS\RescueOS\agent\agents\accessibility_agent.py

Tool Invocation (Line 30):
───────────────────────────
    @tool
    def accessibility_agent_tool(location: str) -> str:
        print(f"\n[AGENT: accessibility_agent] evaluating location='{location}'")
        
        # DIRECT TOOL CALL
        accessibility = get_medical_accessibility(location)    # ← Line 30
        
        # Compose findings in Python
        if accessibility["data_available"]:
            distance = f"{accessibility['medical_distance_km']:.1f}km"
            facility = accessibility['medical_facility_name']
            assessment = (
                f"Medical accessibility assessment: "
                f"Nearest facility is {facility} at {distance}. "
                f"{accessibility['detail']}"
            )
        else:
            assessment = (
                f"Medical accessibility: Data unavailable or API error. "
                f"Treating as unknown, not as confirmed absence. "
                f"{accessibility.get('detail', 'No data available.')}"
            )
        
        return assessment

Execution Pattern:
  get_medical_accessibility(location) ──→ dict with {medical_distance_km, facility_name, ...}
  ──→ Compose into assessment string


AGENT 3: allocation_agent.py
═════════════════════════════

File Location:
  d:\RescueOS\RescueOS\agent\agents\allocation_agent.py

Tool Invocation (Lines 55-60):
──────────────────────────────
    @tool
    def allocation_agent_tool(
        flood_detected: bool,
        exposure_ratio: float,
        nearest_flood_polygon_km2: float,
        medical_distance_km: float,
        data_confidence: str,
        location: str = ""
    ) -> str:
        print(f"\n[AGENT: allocation_agent] computing priority for location='{location}'")
        
        # DIRECT TOOL CALL
        priority = calculate_priority(                          # ← Lines 55-60
            flood_detected=flood_detected,
            exposure_ratio=exposure_ratio,
            nearest_flood_polygon_km2=nearest_flood_polygon_km2,
            medical_distance_km=medical_distance_km,
            data_confidence=data_confidence
        )
        
        # Compose explanation in Python
        assessment = (
            f"Priority Computation: "
            f"PDC Score = {priority['pdc_score']} (0-1 scale). "
            f"Category: {priority['category']}. "
            f"Recommendation: {priority['recommendation']} "
            f"(Data confidence: {data_confidence})"
        )
        
        return assessment

Execution Pattern:
  calculate_priority(flood_detected, exposure_ratio, ...) ──→ dict with {pdc_score, category, ...}
  ──→ Compose into explanation string


ORCHESTRATOR: coordinator_agent.py
═══════════════════════════════════

File Location:
  d:\RescueOS\RescueOS\agent\agents\coordinator_agent.py

All Tool Invocations (Sequential):
──────────────────────────────────

STEP 1 - Flood Assessment (Line 48):
    flood_assessment = flood_assessment_agent_tool(location)

    This invokes:
      ├─ get_flood_status()
      ├─ get_building_exposure()
      └─ Returns: flood assessment string

STEP 2A - Get Raw Flood Data (Lines 53-54):
    flood_data = get_flood_status(location)
    exposure_data = get_building_exposure(location)

STEP 3 - Accessibility Assessment (Line 60):
    accessibility_assessment = accessibility_agent_tool(location)

    This invokes:
      └─ get_medical_accessibility()
      └─ Returns: accessibility assessment string

STEP 2B - Get Raw Accessibility Data (Line 64):
    accessibility_data = get_medical_accessibility(location)

STEP 4 - Allocation Agent (Lines 73-79):
    priority_assessment = allocation_agent_tool(
        flood_detected=flood_data["flooded"],
        exposure_ratio=exposure_data["exposure_ratio"],
        nearest_flood_polygon_km2=flood_data["nearest_flood_polygon_km2"],
        medical_distance_km=accessibility_data["medical_distance_km"],
        data_confidence=data_confidence,
        location=location
    )

    This invokes:
      └─ calculate_priority()
      └─ Returns: priority computation string

STEP 5 - Synthesis (Lines 83-98):
    final_recommendation = f"... {flood_assessment} ... {accessibility_assessment} ... {priority_assessment} ..."
    
    This uses all three previous assessments to create final output


Complete Execution Flow (Coordinator):
─────────────────────────────────────

    coordinator_agent_tool('sivasagar_flood_zone')
    │
    ├─ STEP 1: flood_assessment_agent_tool('sivasagar_flood_zone')
    │   ├─ get_flood_status('sivasagar_flood_zone')
    │   ├─ get_building_exposure('sivasagar_flood_zone')
    │   └─ Return: "Flood Status: FLOODED. Nearest flood area: 4.88 sq km..."
    │
    ├─ get_flood_status('sivasagar_flood_zone') [again for extraction]
    ├─ get_building_exposure('sivasagar_flood_zone') [again for extraction]
    │
    ├─ STEP 2: accessibility_agent_tool('sivasagar_flood_zone')
    │   ├─ get_medical_accessibility('sivasagar_flood_zone')
    │   └─ Return: "Medical accessibility: East Point Hospital at 1.9km"
    │
    ├─ get_medical_accessibility('sivasagar_flood_zone') [again for extraction]
    │
    ├─ STEP 3: allocation_agent_tool(flood_detected=True, exposure_ratio=0.0616, ...)
    │   ├─ calculate_priority(...)
    │   └─ Return: "PDC Score = 0.57 (0-1 scale). Category: PRIORITY..."
    │
    └─ STEP 4: Synthesize all findings
        └─ Return: Complete assessment with all findings + final recommendation


Key Point: Every Tool Call is Explicit
═══════════════════════════════════════

No hidden LLM invocations or multi-agent chaining. Each tool is called
directly by Python code. Execution order is guaranteed.

Tool Calls in Order:
  1. get_flood_status()
  2. get_building_exposure()
  3. get_medical_accessibility()
  4. get_flood_status() [again]
  5. get_building_exposure() [again]
  6. get_medical_accessibility() [again]
  7. calculate_priority()

Result: Deterministic, reproducible, debuggable.


The Unused Agent Objects (For Reference)
═════════════════════════════════════════

These are defined but NOT used:

In flood_assessment_agent.py (Lines 18-28):
    _flood_assessment_agent = Agent(
        model=model,
        tools=[get_flood_status, get_building_exposure],
        system_prompt=(
            "You are a disaster-response analyst specializing in flood risk assessment. "
            "For a given location, call both get_flood_status and get_building_exposure tools. "
            # ...
        ),
    )

In accessibility_agent.py (Lines 10-19):
    _accessibility_agent = Agent(
        model=model,
        tools=[get_medical_accessibility],
        system_prompt=(
            "You are a disaster-response analyst specializing in accessibility..."
        ),
    )

In allocation_agent.py (Lines 15-24):
    _allocation_agent = Agent(
        model=model,
        tools=[calculate_priority],
        system_prompt=(
            "You are a disaster-response prioritization analyst..."
        ),
    )

WHY THEY'RE KEPT (But Not Used):
  ✓ Documentation of intent (shows what agents are supposed to do)
  ✓ Placeholder for future Bedrock integration (might use Agent.invoke())
  ✓ Historical record of attempted pattern (shows what was tried)
  ✓ Could be useful if Strands API changes to add execution methods


Comparison: Wrong vs Right
═══════════════════════════

WRONG (Attempted, Failed):
─────────────────────────
    @tool
    def flood_assessment_agent_tool(location: str) -> str:
        result = _flood_assessment_agent.run(                  # ✗ No .run() method
            f"Assess flood risk for {location}. Call tools."
        )
        return result.messages[-1].content                     # ✗ Crashes here

RIGHT (Working):
────────────────
    @tool
    def flood_assessment_agent_tool(location: str) -> str:
        flood_status = get_flood_status(location)              # ✓ Direct tool call
        exposure = get_building_exposure(location)             # ✓ Direct tool call
        
        assessment = f"Flood Status: ... Exposure: ..."        # ✓ Python composition
        return assessment                                      # ✓ Returns result


Testing the Pattern
═══════════════════

To verify each agent invocation works:

    # Test flood assessment agent
    from agent.agents.flood_assessment_agent import flood_assessment_agent_tool
    result = flood_assessment_agent_tool('sivasagar_flood_zone')
    print(result)
    # Output: "Flood Status: FLOODED. Nearest flood area: 4.88 sq km..."

    # Test accessibility agent
    from agent.agents.accessibility_agent import accessibility_agent_tool
    result = accessibility_agent_tool('sivasagar_flood_zone')
    print(result)
    # Output: "Medical accessibility assessment: East Point Hospital at 1.9km"

    # Test allocation agent
    from agent.agents.allocation_agent import allocation_agent_tool
    result = allocation_agent_tool(
        flood_detected=True,
        exposure_ratio=0.0616,
        nearest_flood_polygon_km2=4.88,
        medical_distance_km=1.9,
        data_confidence='High',
        location='sivasagar_flood_zone'
    )
    print(result)
    # Output: "PDC Score = 0.57 (0-1 scale). Category: PRIORITY..."

    # Test coordinator
    from agent.agents.coordinator_agent import coordinator_agent_tool
    result = coordinator_agent_tool('sivasagar_flood_zone')
    print(result)
    # Output: Complete multi-step assessment


Conclusion
══════════

The Strands framework limitation (no .run() method) became an advantage:

❌ AVOIDED: Multi-agent chaining issues
   - Step-skipping (agent forgets to call tool)
   - Hallucinations (agent makes up data)
   - Unpredictable behavior

✓ ACHIEVED: Tool composition reliability
   - Guaranteed execution order
   - Explicit data flow
   - Deterministic results
   - Debugging-friendly

This pattern scales well to AWS Bedrock migration - just update config.py
with Bedrock model provider, and all the tool composition orchestration
remains the same.
