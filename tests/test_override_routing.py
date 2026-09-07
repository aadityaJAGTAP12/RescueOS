"""
End-to-end test proving the override → routing consumption chain.

This test proves:
1. A route between two points is computed
2. A road on that route exists with geometry
3. Applying an override marking the road blocked causes the route to report the blockage
4. Removing the override causes the route to return to normal

This is NOT a unit test of an isolated function — it proves the full chain:
    Road geometry in repository
    → Active override on that road
    → Routing tool detects the override
    → Route result includes blockage warning
"""

# Repository selection: this module explicitly sets an InMemoryRepository in
# its fresh_repo fixture (override-routing is a pure in-memory unit test of
# route viability). No RELIEFOS_MEMORY env forcing — that poisoned the whole
# pytest process and silently downgraded DATABASE_URL runs to memory mode
# (Item 5B finding).

import pytest
from datetime import datetime, timezone

from agent.data.models import (
    District, Road, Provenance, Override,
)
from agent.data.repository import InMemoryRepository, set_repository, reset_repository, get_repository
from agent.overrides import apply_override, clear_overrides


@pytest.fixture(autouse=True)
def fresh_repo():
    """Provide a fresh InMemoryRepository for each test."""
    reset_repository()
    repo = InMemoryRepository()
    set_repository(repo)
    yield repo
    reset_repository()
    clear_overrides()


@pytest.fixture
def setup_roads(fresh_repo):
    """Create districts and roads with real-ish geometry for Jorhat district."""
    # Create district
    fresh_repo.upsert_district(District(id="jorhat", name="Jorhat", state="Assam"))

    # Create a main road (NH-37 equivalent) — a long road between two points
    # Route from (94.18, 26.74) to (94.22, 26.76) — straight line through the area
    main_road = Road(
        id="road_nh37_jorhat",
        district_id="jorhat",
        name="NH-37 Jorhat",
        highway_type="primary",
        geometry_coords=[
            [94.18, 26.74],
            [94.19, 26.745],
            [94.20, 26.75],
            [94.21, 26.755],
            [94.22, 26.76],
        ],
        flood_affected=False,
        provenance=Provenance.REAL,
    )

    # Create a bridge on the main road
    bridge = Road(
        id="bridge_jorhat_1",
        district_id="jorhat",
        name="Jorhat Bridge",
        highway_type="primary",
        geometry_coords=[
            [94.195, 26.748],
            [94.205, 26.752],
        ],
        flood_affected=False,
        provenance=Provenance.REAL,
        is_bridge=True,
    )

    # Create a secondary road (not on the main route)
    secondary_road = Road(
        id="road_local_jorhat",
        district_id="jorhat",
        name="Gymkhana Road",
        highway_type="residential",
        geometry_coords=[
            [94.15, 26.72],
            [94.16, 26.73],
        ],
        flood_affected=False,
        provenance=Provenance.REAL,
    )

    fresh_repo.upsert_roads([main_road, bridge, secondary_road])
    return main_road, bridge, secondary_road


class TestOverrideRoutingChain:
    """End-to-end test proving override → routing consumption."""

    def test_route_without_override_has_no_blockage_warning(self, setup_roads):
        """Route computed without any override has no blockage warning."""
        from agent.tools.routing_tool import get_route

        # Route between two points that would cross the main road
        route = get_route(
            start_lat=26.74,
            start_lon=94.18,
            end_lat=26.76,
            end_lon=94.22,
        )

        # Route should exist (either OSRM or haversine fallback)
        assert route["distance_km"] > 0
        assert "geometry" in route

        # No override warning
        assert route.get("crosses_overridden_road", False) is False
        assert route.get("blocked_segments", []) == []
        assert route.get("override_warning") is None

    def test_route_with_override_reports_blockage(self, setup_roads):
        """After applying override marking road blocked, route reports blockage."""
        from agent.tools.routing_tool import get_route

        # First, get route without override
        route_before = get_route(
            start_lat=26.74,
            start_lon=94.18,
            end_lat=26.76,
            end_lon=94.22,
        )
        assert route_before.get("crosses_overridden_road", False) is False
        assert route_before.get("route_valid") is True
        assert route_before.get("requires_reroute") is False

        # Apply override marking the main road as blocked
        apply_override(
            target_type="road",
            target_id="NH-37 Jorhat",
            new_status="blocked",
            reason="Bridge washed out by flood",
            actor="field_team_1",
        )

        # Recompute the same route
        route_after = get_route(
            start_lat=26.74,
            start_lon=94.18,
            end_lat=26.76,
            end_lon=94.22,
        )

        # Route should now report the blockage
        assert route_after.get("crosses_overridden_road") is True
        blocked = route_after.get("blocked_segments", [])
        assert len(blocked) >= 1
        assert any("NH-37" in s["road_name"] for s in blocked)
        assert blocked[0]["override_status"] == "blocked"
        assert "blocked" in (route_after.get("override_warning") or "").lower()

        # CRITICAL: Honest labeling — route is NOT valid
        assert route_after.get("route_valid") is False
        assert route_after.get("requires_reroute") is True
        assert route_after.get("route_valid_reason") is not None
        assert "blocked" in route_after["route_valid_reason"].lower()

    def test_route_after_removing_override_returns_to_normal(self, setup_roads):
        """After removing the override, route returns to normal (no blockage warning)."""
        from agent.tools.routing_tool import get_route

        # Apply override
        apply_override(
            target_type="road",
            target_id="NH-37 Jorhat",
            new_status="blocked",
            reason="Test blockage",
        )

        # Verify override is detected
        route_blocked = get_route(
            start_lat=26.74,
            start_lon=94.18,
            end_lat=26.76,
            end_lon=94.22,
        )
        assert route_blocked.get("crosses_overridden_road") is True
        assert route_blocked.get("route_valid") is False
        assert route_blocked.get("requires_reroute") is True

        # Remove the override
        clear_overrides()

        # Recompute route — should be back to normal
        route_clear = get_route(
            start_lat=26.74,
            start_lon=94.18,
            end_lat=26.76,
            end_lon=94.22,
        )
        assert route_clear.get("crosses_overridden_road") is False
        assert route_clear.get("blocked_segments", []) == []
        assert route_clear.get("route_valid") is True
        assert route_clear.get("requires_reroute") is False

    def test_override_on_bridge_detected(self, setup_roads):
        """Override on a bridge is also detected by the routing tool."""
        from agent.tools.routing_tool import get_route

        # Apply override on the bridge
        apply_override(
            target_type="road",
            target_id="Jorhat Bridge",
            new_status="submerged",
            reason="Bridge submerged by flood water",
            actor="coordinator",
        )

        route = get_route(
            start_lat=26.74,
            start_lon=94.18,
            end_lat=26.76,
            end_lon=94.22,
        )

        # Should detect the bridge blockage
        assert route.get("crosses_overridden_road") is True
        blocked = route.get("blocked_segments", [])
        assert any("Bridge" in s["road_name"] for s in blocked)
        assert blocked[0]["override_status"] == "submerged"

    def test_route_not_affected_by_unrelated_override(self, setup_roads):
        """Override on a road NOT on the route doesn't affect the route."""
        from agent.tools.routing_tool import get_route

        # Apply override on Gymkhana Road (not on the main route)
        apply_override(
            target_type="road",
            target_id="Gymkhana Road",
            new_status="blocked",
            reason="Construction",
        )

        route = get_route(
            start_lat=26.74,
            start_lon=94.18,
            end_lat=26.76,
            end_lon=94.22,
        )

        # Route should NOT report blockage (Gymkhana Road is far from the route)
        assert route.get("crosses_overridden_road") is False
        assert route.get("blocked_segments", []) == []
        assert route.get("route_valid") is True
        assert route.get("requires_reroute") is False

    def test_override_preserves_original_routing_behavior(self, setup_roads):
        """When no override is active, routing behavior is unchanged."""
        from agent.tools.routing_tool import get_route

        # Get route twice — should be consistent
        route1 = get_route(
            start_lat=26.74,
            start_lon=94.18,
            end_lat=26.76,
            end_lon=94.22,
        )
        route2 = get_route(
            start_lat=26.74,
            start_lon=94.18,
            end_lat=26.76,
            end_lon=94.22,
        )

        # Distance and geometry should be identical
        assert route1["distance_km"] == route2["distance_km"]
        assert route1["geometry"] == route2["geometry"]
        assert route1.get("crosses_overridden_road") == route2.get("crosses_overridden_road")
