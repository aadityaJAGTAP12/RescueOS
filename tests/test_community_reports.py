"""
Tests for community reports: validation, serialization, and query behavior.

All tests use a temporary file for report storage to avoid polluting the
real data directory.
"""

import json
import os
import pytest
from unittest.mock import patch
from agent import community_reports as cr


@pytest.fixture(autouse=True)
def _isolated_reports(tmp_path, monkeypatch):
    """Redirect report storage to a temp directory for every test."""
    reports_file = str(tmp_path / "community_reports.json")
    monkeypatch.setattr(cr, "REPORTS_FILE", reports_file)
    # Also reset in-memory state
    cr._save_reports([])
    yield
    cr._save_reports([])


class TestSubmitReport:
    """Tests for submit_report() validation."""

    def test_valid_report_accepted(self, tmp_path):
        """A valid report from a flood zone should be accepted."""
        # Mock flood zone check to return True
        with patch.object(cr, "_is_near_flood_zone", return_value=True):
            result = cr.submit_report(
                lat=26.9894,
                lon=94.6698,
                people_count=15,
                adults=10,
                children=3,
                elderly=2,
                needs=["food", "medical"],
                note="Family trapped on roof",
            )
        assert result["success"] is True
        assert result["report_id"] is not None
        assert "accepted" in result["message"].lower()

    def test_invalid_needs_category_rejected(self):
        """Reports with invalid need categories should be rejected."""
        with patch.object(cr, "_is_near_flood_zone", return_value=True):
            result = cr.submit_report(
                lat=26.9894,
                lon=94.6698,
                people_count=5,
                needs=["food", "invalid_category"],
            )
        assert result["success"] is False
        assert "invalid" in result["message"].lower()

    def test_out_of_flood_area_rejected(self):
        """Reports from non-flood areas should be rejected."""
        with patch.object(cr, "_is_near_flood_zone", return_value=False):
            result = cr.submit_report(
                lat=28.0,  # Far from any flood zone
                lon=95.0,
                people_count=5,
                needs=["food"],
            )
        assert result["success"] is False
        assert "flood" in result["message"].lower()

    def test_report_serialization(self):
        """Submitted report should be stored as valid JSON."""
        with patch.object(cr, "_is_near_flood_zone", return_value=True):
            cr.submit_report(
                lat=26.99,
                lon=94.67,
                people_count=10,
                needs=["water"],
                note="Urgent",
                contact="test@example.com",
            )
        reports = cr.get_all_reports()
        assert len(reports) == 1
        r = reports[0]
        assert r["lat"] == 26.99
        assert r["lon"] == 94.67
        assert r["people_count"] == 10
        assert r["needs"] == ["water"]
        assert r["note"] == "Urgent"
        assert r["contact"] == "test@example.com"
        assert r["source"] == "community_report"
        assert r["verified"] is False
        assert "id" in r
        assert "timestamp" in r


class TestGetReportsNear:
    """Tests for get_reports_near() spatial query."""

    def test_returns_nearby_reports(self):
        """Reports within radius should be returned."""
        with patch.object(cr, "_is_near_flood_zone", return_value=True):
            cr.submit_report(lat=26.99, lon=94.67, people_count=10, needs=["food"])

        nearby = cr.get_reports_near(26.99, 94.67, radius_km=5.0)
        assert len(nearby) == 1
        assert "distance_km" in nearby[0]

    def test_excludes_distant_reports(self):
        """Reports outside the radius should not be returned."""
        with patch.object(cr, "_is_near_flood_zone", return_value=True):
            cr.submit_report(lat=26.99, lon=94.67, people_count=10, needs=["food"])

        # Search far away
        nearby = cr.get_reports_near(28.0, 96.0, radius_km=1.0)
        assert len(nearby) == 0

    def test_sorted_by_distance(self):
        """Results should be sorted by distance ascending."""
        with patch.object(cr, "_is_near_flood_zone", return_value=True):
            cr.submit_report(lat=26.99, lon=94.67, people_count=5, needs=["food"])
            cr.submit_report(lat=26.995, lon=94.675, people_count=3, needs=["water"])

        nearby = cr.get_reports_near(26.99, 94.67, radius_km=5.0)
        if len(nearby) >= 2:
            assert nearby[0]["distance_km"] <= nearby[1]["distance_km"]


class TestClearReports:
    """Tests for clear_reports()."""

    def test_clear_empties_reports(self):
        """clear_reports() should remove all stored reports."""
        with patch.object(cr, "_is_near_flood_zone", return_value=True):
            cr.submit_report(lat=26.99, lon=94.67, people_count=5, needs=["food"])
            cr.submit_report(lat=26.99, lon=94.67, people_count=3, needs=["water"])

        assert len(cr.get_all_reports()) == 2
        cr.clear_reports()
        assert len(cr.get_all_reports()) == 0
