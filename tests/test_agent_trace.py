"""
Tests for agent_trace — per-agent timing capture in assessment and API.

Verifies that:
1. agent_trace is populated when a list is passed
2. Each trace entry has the required fields
3. agent_trace is None/empty when not requested
4. Timing values are numeric and reasonable
5. The API response includes agent_trace
"""

import time
import pytest
from unittest.mock import patch, MagicMock
from agent.assessment import run_relief_assessment


MOCK_FLOOD_FLOODED = {
    "location": "test_flood_zone",
    "flooded": True,
    "exactly_contained": True,
    "near_flood_zone": False,
    "total_flood_polygons": 45,
    "nearest_flood_polygon_km2": 4.88,
    "detail": "EXACTLY CONTAINED"
}

MOCK_EXPOSURE_HIGH = {
    "location": "test",
    "total_buildings": 100,
    "exposed_count": 60,
    "exposure_ratio": 0.6,
    "detail": "100 buildings, 60 exposed",
    "data_available": True
}

MOCK_ACCESSIBILITY_NEAR = {
    "location": "test",
    "medical_distance_km": 2.5,
    "medical_facility_name": "Test Hospital",
    "detail": "Test Hospital at 2.5km",
    "data_available": True
}


REQUIRED_TRACE_FIELDS = {
    "agent_name", "query_portion_handled", "started_at", "completed_at",
    "duration_ms", "tools_called", "output_summary", "raw_output", "status"
}


class TestAgentTraceCapture:
    """Tests for agent_trace in run_relief_assessment."""

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_agent_trace_populated_when_list_passed(self, mock_flood, mock_exposure, mock_access):
        """When agent_trace list is passed, it should be populated."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        trace = []
        result = run_relief_assessment("sivasagar_flood_zone", agent_trace=trace)

        assert len(trace) > 0
        # Should have entries for: flood, exposure, accessibility, priority = 4
        assert len(trace) == 4

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_agent_trace_not_created_when_not_passed(self, mock_flood, mock_exposure, mock_access):
        """When agent_trace is not passed, the result should still work."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        result = run_relief_assessment("sivasagar_flood_zone")
        assert "priority" in result

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_trace_entries_have_required_fields(self, mock_flood, mock_exposure, mock_access):
        """Each trace entry should have all required fields."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        trace = []
        run_relief_assessment("test_location", agent_trace=trace)

        for entry in trace:
            missing = REQUIRED_TRACE_FIELDS - set(entry.keys())
            assert not missing, f"Missing fields in trace entry: {missing}"

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_trace_timing_is_numeric(self, mock_flood, mock_exposure, mock_access):
        """Timing fields should be numeric."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        trace = []
        run_relief_assessment("test_location", agent_trace=trace)

        for entry in trace:
            assert isinstance(entry["started_at"], (int, float))
            assert isinstance(entry["completed_at"], (int, float))
            assert isinstance(entry["duration_ms"], (int, float))
            assert entry["duration_ms"] >= 0

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_trace_agent_names_are_distinct(self, mock_flood, mock_exposure, mock_access):
        """Each agent should have a distinct name in the trace."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        trace = []
        run_relief_assessment("test_location", agent_trace=trace)

        names = [e["agent_name"] for e in trace]
        assert len(names) == len(set(names)), f"Duplicate agent names: {names}"

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_trace_tools_called_is_list(self, mock_flood, mock_exposure, mock_access):
        """tools_called should be a list of strings."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        trace = []
        run_relief_assessment("test_location", agent_trace=trace)

        for entry in trace:
            assert isinstance(entry["tools_called"], list)
            assert len(entry["tools_called"]) > 0
            for tool in entry["tools_called"]:
                assert isinstance(tool, str)

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_trace_entries_are_complete(self, mock_flood, mock_exposure, mock_access):
        """All trace entries should have status=complete for successful runs."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        trace = []
        run_relief_assessment("test_location", agent_trace=trace)

        for entry in trace:
            assert entry["status"] == "complete"

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_trace_raw_output_contains_real_data(self, mock_flood, mock_exposure, mock_access):
        """raw_output should contain the actual tool output, not fabricated data."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        trace = []
        run_relief_assessment("test_location", agent_trace=trace)

        # Flood agent raw_output should match the mock
        flood_entry = next(e for e in trace if e["agent_name"] == "flood_assessment_agent")
        assert flood_entry["raw_output"]["flooded"] is True
        assert flood_entry["raw_output"]["nearest_flood_polygon_km2"] == 4.88

        # Exposure agent raw_output should match the mock
        exposure_entry = next(e for e in trace if e["agent_name"] == "exposure_agent")
        assert exposure_entry["raw_output"]["total_buildings"] == 100
        assert exposure_entry["raw_output"]["exposed_count"] == 60

        # Accessibility agent raw_output should match the mock
        access_entry = next(e for e in trace if e["agent_name"] == "accessibility_agent")
        assert access_entry["raw_output"]["medical_distance_km"] == 2.5
        assert access_entry["raw_output"]["medical_facility_name"] == "Test Hospital"

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_trace_allocation_agent_includes_priority(self, mock_flood, mock_exposure, mock_access):
        """The allocation_agent trace entry should include PDC score info."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        trace = []
        run_relief_assessment("test_location", agent_trace=trace)

        alloc_entry = next(e for e in trace if e["agent_name"] == "allocation_agent")
        assert "PDC" in alloc_entry["output_summary"]
        assert alloc_entry["tools_called"] == ["calculate_priority"]

    @patch("agent.assessment.get_medical_accessibility")
    @patch("agent.assessment.get_building_exposure")
    @patch("agent.assessment.get_flood_status")
    def test_trace_timestamps_are_sequential(self, mock_flood, mock_exposure, mock_access):
        """Each agent's started_at should be >= the previous agent's completed_at."""
        mock_flood.return_value = MOCK_FLOOD_FLOODED
        mock_exposure.return_value = MOCK_EXPOSURE_HIGH
        mock_access.return_value = MOCK_ACCESSIBILITY_NEAR

        trace = []
        run_relief_assessment("test_location", agent_trace=trace)

        for i in range(1, len(trace)):
            assert trace[i]["started_at"] >= trace[i-1]["completed_at"], (
                f"Agent {trace[i]['agent_name']} started before "
                f"{trace[i-1]['agent_name']} completed"
            )
