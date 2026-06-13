"""Unit tests for app.utils.geo — Haversine and impossible-travel logic."""

import pytest

from app.utils.geo import haversine_km, is_impossible_travel


class TestHaversine:
    def test_same_point_is_zero(self):
        """Distance from a point to itself must be zero."""
        assert haversine_km(51.5, -0.1, 51.5, -0.1) == pytest.approx(0.0, abs=0.001)

    def test_london_to_paris_approx(self):
        """London → Paris is roughly 340 km."""
        # London ~(51.51, -0.13), Paris ~(48.85, 2.35)
        dist = haversine_km(51.51, -0.13, 48.85, 2.35)
        assert 330 < dist < 360

    def test_new_york_to_los_angeles(self):
        """New York → Los Angeles is roughly 3,940 km."""
        dist = haversine_km(40.71, -74.01, 34.05, -118.24)
        assert 3800 < dist < 4100

    def test_antipodal_points(self):
        """Opposite poles span roughly 20,015 km (half earth circumference)."""
        dist = haversine_km(90.0, 0.0, -90.0, 0.0)
        assert 19900 < dist < 20200


class TestImpossibleTravel:
    def test_short_distance_is_not_impossible(self):
        """100 km in 0.5 h is not impossible travel (distance ≤ threshold)."""
        assert is_impossible_travel(
            lat1=51.5, lon1=-0.1,
            lat2=52.0, lon2=-0.1,   # ~55 km north of London
            hours_elapsed=0.5,
            max_distance_km=500.0,
            min_hours=2.0,
        ) is False

    def test_impossible_travel_detected(self):
        """London to New York in 1 hour is physically impossible."""
        dist = haversine_km(51.51, -0.13, 40.71, -74.01)  # ~5,500 km
        assert dist > 500
        assert is_impossible_travel(
            lat1=51.51, lon1=-0.13,
            lat2=40.71, lon2=-74.01,
            hours_elapsed=1.0,
            max_distance_km=500.0,
            min_hours=2.0,
        ) is True

    def test_elapsed_time_exceeds_min_hours_not_impossible(self):
        """If enough time has passed the trip is never flagged, regardless of distance."""
        assert is_impossible_travel(
            lat1=51.51, lon1=-0.13,
            lat2=40.71, lon2=-74.01,
            hours_elapsed=3.0,   # > min_hours=2
            max_distance_km=500.0,
            min_hours=2.0,
        ) is False

    def test_boundary_exactly_at_min_hours(self):
        """Exactly at min_hours the trip is not flagged (>= check)."""
        assert is_impossible_travel(
            lat1=0.0, lon1=0.0,
            lat2=10.0, lon2=10.0,
            hours_elapsed=2.0,
            max_distance_km=100.0,
            min_hours=2.0,
        ) is False
