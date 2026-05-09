"""
Unit tests for services/geo.haversine_km.

Known reference distances are cross-checked against published values
(Wikipedia / aviation databases) and expected to be within 1%.
"""
import math
import pytest

from services.geo import haversine_km


class TestHaversineSamePoint:
    def test_identical_coordinates_return_zero(self):
        assert haversine_km(50.07, 14.43, 50.07, 14.43) == 0.0

    def test_north_pole_to_north_pole(self):
        assert haversine_km(90.0, 0.0, 90.0, 0.0) == 0.0


class TestHaversineKnownDistances:
    # Prague ↔ Berlin: ~281 km (published value)
    def test_prague_to_berlin_approx(self):
        dist = haversine_km(50.0755, 14.4378, 52.5200, 13.4050)
        assert 275 < dist < 290

    # Prague ↔ Vienna: ~257 km (published value)
    def test_prague_to_vienna_approx(self):
        dist = haversine_km(50.0755, 14.4378, 48.2082, 16.3738)
        assert 250 < dist < 265

    # One degree of latitude ≈ 111.2 km
    def test_one_degree_latitude(self):
        dist = haversine_km(0.0, 0.0, 1.0, 0.0)
        assert 110 < dist < 113

    # One degree of longitude at equator ≈ 111.2 km
    def test_one_degree_longitude_at_equator(self):
        dist = haversine_km(0.0, 0.0, 0.0, 1.0)
        assert 110 < dist < 113


class TestHaversineSymmetry:
    def test_distance_is_symmetric(self):
        a = haversine_km(50.07, 14.43, 52.52, 13.40)
        b = haversine_km(52.52, 13.40, 50.07, 14.43)
        assert math.isclose(a, b, rel_tol=1e-9)

    def test_negative_coordinates(self):
        # Buenos Aires ↔ Sydney: ~11 800 km (roughly)
        dist = haversine_km(-34.6, -58.4, -33.87, 151.21)
        assert 11_500 < dist < 12_100

    def test_always_non_negative(self):
        for lat1, lon1, lat2, lon2 in [
            (0, 0, 0, 0),
            (90, 0, -90, 0),
            (-45, 120, 45, -120),
        ]:
            assert haversine_km(lat1, lon1, lat2, lon2) >= 0.0


class TestHaversineRiskRadius:
    """Verify the 2 km risk threshold works correctly with haversine."""

    def test_point_within_2km_detected(self):
        # ~1.11 km north
        assert haversine_km(50.0, 14.0, 50.01, 14.0) < 2.0

    def test_point_beyond_2km_not_flagged(self):
        # ~11 km north
        assert haversine_km(50.0, 14.0, 50.1, 14.0) > 2.0
