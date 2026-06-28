"""Tests for the value-based detectors (divergence, error burst, freeze, jump, range)."""

from robot_triage.detectors.divergence import DivergenceDetector
from robot_triage.detectors.error_burst import ErrorBurstDetector
from robot_triage.detectors.freeze import FreezeDetector
from robot_triage.detectors.jump import JumpDetector
from robot_triage.detectors.range_check import RangeDetector


def twist(x, z):
    return {"linear": {"x": x}, "angular": {"z": z}}


def odom(x, z):
    return {"twist": {"twist": {"linear": {"x": x}, "angular": {"z": z}}}}


def test_divergence_flags_a_stuck_robot():
    d = DivergenceDetector()
    for i in range(60):
        t = i * 0.1
        d.process("/cmd_vel", t, twist(0.5, 0.0))
        # Commanded 0.5 m/s, but actual ~0 the whole time.
        d.process("/odom", t, odom(0.0, 0.0))
    events = d.finish()
    assert len(events) == 1
    assert events[0].detector == "divergence"
    assert events[0].details["axis"] == "linear.x"


def test_divergence_ignores_matching_motion():
    d = DivergenceDetector()
    for i in range(60):
        t = i * 0.1
        d.process("/cmd_vel", t, twist(0.5, 0.2))
        d.process("/odom", t, odom(0.5, 0.2))
    assert d.finish() == []


def test_error_burst_needs_enough_errors():
    d = ErrorBurstDetector(threshold=5)
    # Only 3 errors -> below threshold.
    for i in range(3):
        d.process("/rosout", i * 0.1, {"level": 40, "msg": "boom"})
    assert d.finish() == []


def test_error_burst_flags_a_cluster():
    d = ErrorBurstDetector(threshold=5)
    for i in range(8):
        d.process("/rosout", i * 0.1, {"level": 40, "msg": "overcurrent"})
    events = d.finish()
    assert len(events) == 1
    assert events[0].details["count"] == 8
    assert "overcurrent" in events[0].details["first_message"]


def test_info_level_logs_are_ignored():
    d = ErrorBurstDetector(threshold=5)
    for i in range(8):
        d.process("/rosout", i * 0.1, {"level": 20, "msg": "hello"})  # INFO
    assert d.finish() == []


def test_freeze_flags_a_stuck_value():
    d = FreezeDetector(min_freeze_s=1.0, min_count=5)
    for i in range(20):           # varies
        d.process("/imu", i * 0.1, {"v": i})
    for i in range(20):           # stuck for 2s
        d.process("/imu", 2.0 + i * 0.1, {"v": 999})
    events = d.finish()
    assert len(events) == 1
    assert events[0].detector == "freeze"


def test_constant_topic_is_not_a_freeze():
    # Never varies -> constant by design, must not fire.
    d = FreezeDetector(min_freeze_s=1.0, min_count=5)
    for i in range(50):
        d.process("/tf_config", i * 0.1, {"v": 7})
    assert d.finish() == []


def test_jump_flags_a_teleport():
    d = JumpDetector(min_samples=5)
    x = 0.0
    for i in range(30):
        x += 0.05
        if i == 15:
            x += 5.0              # teleport
        d.process("/odom", i * 0.1, {"pose": {"pose": {"position": {"x": x}}}})
    events = d.finish()
    assert len(events) == 1
    assert events[0].details["jump_meters"] > 4.0


def test_smooth_odometry_has_no_jump():
    d = JumpDetector(min_samples=5)
    x = 0.0
    for i in range(30):
        x += 0.05
        d.process("/odom", i * 0.1, {"pose": {"pose": {"position": {"x": x}}}})
    assert d.finish() == []


def test_range_flags_sustained_excursion():
    rules = (("/battery_state", "percentage", 0.0, 1.0, "battery %"),)
    d = RangeDetector(rules=rules, min_duration_s=0.4)
    for i in range(10):
        d.process("/battery_state", i * 0.1, {"percentage": 1.4})  # >100%
    events = d.finish()
    assert len(events) == 1
    assert events[0].details["worst_value"] == 1.4


def test_range_flags_nan():
    rules = (("/pose", "z", -100.0, 100.0, "z"),)
    d = RangeDetector(rules=rules, min_duration_s=0.0)
    for i in range(5):
        d.process("/pose", i * 0.1, {"z": float("nan")})
    events = d.finish()
    assert len(events) == 1
    assert "NaN" in events[0].summary


def test_range_ignores_brief_blip():
    rules = (("/battery_state", "percentage", 0.0, 1.0, "battery %"),)
    d = RangeDetector(rules=rules, min_duration_s=0.5)
    d.process("/battery_state", 0.0, {"percentage": 1.4})   # single blip
    d.process("/battery_state", 0.1, {"percentage": 0.8})   # back in range
    assert d.finish() == []
