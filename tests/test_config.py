"""Tests for config loading and config-driven detector construction."""

import pytest

from robot_triage.config import load_config
from robot_triage.detectors import DETECTOR_CLASSES, build_detectors


def _by_name(detectors):
    return {d.name: d for d in detectors}


def test_defaults_build_all_detectors():
    dets = build_detectors()
    assert set(_by_name(dets)) == set(DETECTOR_CLASSES)


def test_enabled_false_skips_a_detector():
    dets = build_detectors({"detectors": {"error_burst": {"enabled": False}}})
    names = _by_name(dets)
    assert "error_burst" not in names
    assert len(names) == len(DETECTOR_CLASSES) - 1


def test_override_topic_and_threshold():
    dets = build_detectors(
        {"detectors": {"jump": {"topic": "/camera/odom/sample", "min_jump_m": 0.3}}}
    )
    jump = _by_name(dets)["jump"]
    assert jump.topic == "/camera/odom/sample"
    assert jump.min_jump_m == 0.3


def test_range_rules_from_list_of_dicts():
    cfg = {"detectors": {"range": {"rules": [
        {"topic": "/b", "field": "v", "low": 0.0, "high": 1.0, "label": "b"}
    ]}}}
    rng = _by_name(build_detectors(cfg))["range"]
    assert rng.rules[0] == ("/b", "v", 0.0, 1.0, "b")


def test_unknown_detector_warns_but_does_not_crash(capsys):
    dets = build_detectors({"detectors": {"ghost": {"x": 1}}})
    assert len(dets) == len(DETECTOR_CLASSES)  # real ones still built
    assert "unknown detector 'ghost'" in capsys.readouterr().err


def test_bad_constructor_kwarg_exits_cleanly():
    with pytest.raises(SystemExit):
        build_detectors({"detectors": {"dropout": {"not_a_param": 1}}})


def test_load_yaml(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("detectors:\n  jump:\n    topic: /x\n")
    assert load_config(p)["detectors"]["jump"]["topic"] == "/x"


def test_load_json(tmp_path):
    p = tmp_path / "c.json"
    p.write_text('{"detectors": {"jump": {"topic": "/y"}}}')
    assert load_config(p)["detectors"]["jump"]["topic"] == "/y"


def test_load_none_and_empty(tmp_path):
    assert load_config(None) == {}
    empty = tmp_path / "e.yaml"
    empty.write_text("")
    assert load_config(empty) == {}
