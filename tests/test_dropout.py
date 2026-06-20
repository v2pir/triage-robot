"""Tests for the dropout detector.

These feed synthetic messages straight into the detector -- no bag file needed,
so they're fast and don't depend on mcap/rosbags.
"""

from robot_triage.detectors.dropout import DropoutDetector


def _feed(detector, topic, times):
    for t in times:
        detector.process(topic, t, None)
    return detector.finish()


def test_flags_a_clear_gap():
    # 12 msgs at 0.1s, a 3s silence, then 12 more.
    times = [i * 0.1 for i in range(12)]
    times += [times[-1] + 3.0 + i * 0.1 for i in range(12)]

    events = _feed(DropoutDetector(), "/camera", times)

    assert len(events) == 1
    e = events[0]
    assert e.detector == "dropout"
    assert e.details["topic"] == "/camera"
    assert 2.9 < e.details["gap_seconds"] < 3.1


def test_steady_stream_is_silent():
    times = [i * 0.1 for i in range(100)]
    assert _feed(DropoutDetector(), "/imu", times) == []


def test_too_few_messages_is_ignored():
    # Fewer than min_samples: not enough data to judge, even with a big gap.
    events = _feed(DropoutDetector(), "/lidar", [0.0, 0.1, 5.0])
    assert events == []
