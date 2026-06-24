"""Tests for single-pass clip extraction."""

from dataclasses import dataclass

from robot_triage.reader import read_messages
from robot_triage.replay import extract_clips
from tests.test_edge_cases import write_mcap


@dataclass
class FakeEvent:
    detector: str
    t_start: float
    t_end: float


def test_extracts_one_clip_per_event_in_single_pass(tmp_path):
    # 100 messages at 0.1s spacing on two topics (0..9.9s).
    base = 1_000_000_000
    msgs = []
    for i in range(100):
        t = base + i * 100_000_000
        msgs.append(("/a", t, {"i": i}))
        msgs.append(("/b", t, {"i": i}))
    src = tmp_path / "src.mcap"
    write_mcap(src, msgs)

    # Two events at 2s and 8s; pad 1s -> windows [1,3] and [7,9].
    events = [FakeEvent("x", 2.0, 2.0), FakeEvent("y", 8.0, 8.0)]
    out = tmp_path / "clips"
    paths = extract_clips(str(src), events, str(out), pad_s=1.0)

    assert len(paths) == 2

    # First clip should hold ~[1,3]s of both topics and nothing from 8s.
    times = [t for _topic, t, _msg in read_messages(paths[0])]
    assert times, "clip should not be empty"
    assert max(times) - min(times) <= 2.1
    topics = {topic for topic, _t, _msg in read_messages(paths[0])}
    assert topics == {"/a", "/b"}  # full context preserved


def test_no_events_writes_nothing(tmp_path):
    src = tmp_path / "src.mcap"
    write_mcap(src, [("/a", 1_000_000_000, {"i": 0})])
    assert extract_clips(str(src), [], str(tmp_path / "clips")) == []
