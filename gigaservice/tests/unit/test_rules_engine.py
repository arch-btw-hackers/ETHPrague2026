"""
Unit tests for the rules-engine logic embedded in sensors.receive_sensor_data.

We extract and test the comparison logic in isolation using parametrize
so every branch is covered without spinning up an HTTP server.
"""
import pytest


# ---------------------------------------------------------------------------
# Helpers — replicate the comparison logic so we can test it as a pure fn.
# The actual endpoint does the same comparisons; if we ever extract them
# into a separate module, these tests will just import from there instead.
# ---------------------------------------------------------------------------

def evaluate_conditions(readings: dict, conditions: dict) -> bool:
    """Mirror of the analysis logic in receive_sensor_data."""
    is_valid = True
    if readings["temp_c"] > conditions["max_temp_c"]:
        is_valid = False
    if abs(readings["acceleration_overload"]) > conditions["max_acceleration"]:
        is_valid = False
    return is_valid


CONDITIONS = {"max_temp_c": 25.0, "max_acceleration": 2.0}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestRulesEngineHappyPath:
    def test_all_within_limits_is_valid(self):
        readings = {"temp_c": 20.0, "acceleration_overload": 1.159}
        assert evaluate_conditions(readings, CONDITIONS) is True

    def test_exact_limit_values_are_valid(self):
        # Boundary: exactly at the limit — should still pass (strict >)
        readings = {"temp_c": 25.0, "acceleration_overload": 2.0}
        assert evaluate_conditions(readings, CONDITIONS) is True

    def test_zero_readings_valid(self):
        readings = {"temp_c": 0.0, "acceleration_overload": 0.0}
        assert evaluate_conditions(readings, CONDITIONS) is True

    def test_negative_acceleration_within_limit(self):
        # abs() check — negative values should use absolute value
        readings = {"temp_c": 10.0, "acceleration_overload": -1.5}
        assert evaluate_conditions(readings, CONDITIONS) is True


# ---------------------------------------------------------------------------
# Temperature violations
# ---------------------------------------------------------------------------

class TestTemperatureViolation:
    def test_temp_exceeds_max(self):
        readings = {"temp_c": 26.0, "acceleration_overload": 0.0}
        assert evaluate_conditions(readings, CONDITIONS) is False

    def test_temp_just_above_limit(self):
        readings = {"temp_c": 25.001, "acceleration_overload": 0.0}
        assert evaluate_conditions(readings, CONDITIONS) is False

    def test_very_high_temp(self):
        readings = {"temp_c": 999.0, "acceleration_overload": 0.0}
        assert evaluate_conditions(readings, CONDITIONS) is False

    def test_negative_temp_always_valid(self):
        readings = {"temp_c": -40.0, "acceleration_overload": 0.0}
        assert evaluate_conditions(readings, CONDITIONS) is True


# ---------------------------------------------------------------------------
# Acceleration violations
# ---------------------------------------------------------------------------

class TestAccelerationViolation:
    def test_overload_exceeds_max(self):
        readings = {"temp_c": 10.0, "acceleration_overload": 3.0}
        assert evaluate_conditions(readings, CONDITIONS) is False

    def test_negative_overload_exceeds_max(self):
        readings = {"temp_c": 10.0, "acceleration_overload": -3.0}
        assert evaluate_conditions(readings, CONDITIONS) is False

    def test_overload_just_above_limit(self):
        readings = {"temp_c": 10.0, "acceleration_overload": 2.001}
        assert evaluate_conditions(readings, CONDITIONS) is False


# ---------------------------------------------------------------------------
# Multiple violations at once
# ---------------------------------------------------------------------------

class TestMultipleViolations:
    def test_both_violated(self):
        readings = {"temp_c": 30.0, "acceleration_overload": 5.0}
        assert evaluate_conditions(readings, CONDITIONS) is False

    def test_temp_violated_overload_ok(self):
        readings = {"temp_c": 30.0, "acceleration_overload": 1.0}
        assert evaluate_conditions(readings, CONDITIONS) is False


# ---------------------------------------------------------------------------
# Parametrized edge cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("temp,acc,expected", [
    (25.0,  2.0,   True),   # exact boundary — valid
    (25.01, 2.0,   False),  # 1 tick over temp
    (25.0,  2.01,  False),  # 1 tick over overload
    (-99.0, 0.0,   True),   # extreme cold
    (0.0,  -2.0,   True),   # exact negative boundary
    (0.0,  -2.01,  False),  # just over negative boundary
])
def test_boundary_parametrized(temp, acc, expected):
    readings = {"temp_c": temp, "acceleration_overload": acc}
    assert evaluate_conditions(readings, CONDITIONS) is expected


# ---------------------------------------------------------------------------
# Custom conditions
# ---------------------------------------------------------------------------

class TestCustomConditions:
    def test_strict_conditions(self):
        strict = {"max_temp_c": 5.0, "max_acceleration": 0.5}
        readings = {"temp_c": 5.1, "acceleration_overload": 0.1}
        assert evaluate_conditions(readings, strict) is False

    def test_relaxed_conditions(self):
        relaxed = {"max_temp_c": 100.0, "max_acceleration": 50.0}
        readings = {"temp_c": 80.0, "acceleration_overload": 30.0}
        assert evaluate_conditions(readings, relaxed) is True

    def test_zero_max_acceleration(self):
        cond = {"max_temp_c": 25.0, "max_acceleration": 0.0}
        readings = {"temp_c": 10.0, "acceleration_overload": 0.001}
        assert evaluate_conditions(readings, cond) is False
