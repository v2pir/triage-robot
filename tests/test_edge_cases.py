"""Universality / robustness tests: weird bags must not crash the pipeline.

These build tiny .mcap files on the fly (mcap is a hard dependency) and push
them through the real reader + detectors + CLI.
"""

import json

from mcap.writer import Writer

from robot_triage.cli import main, run
from robot_triage.reader import bag_start_ns


def write_mcap(path, messages, encoding="json"):
    """messages: list of (topic, log_time_ns, json-able object)."""
    with open(path, "wb") as f:
        w = Writer(f)
        w.start()
        schema = w.register_schema(name="X", encoding="jsonschema", data=b"{}")
        channels = {}
        for topic, t, obj in messages:
            if topic not in channels:
                channels[topic] = w.register_channel(
                    topic=topic, message_encoding=encoding, schema_id=schema
                )
            data = json.dumps(obj).encode() if encoding == "json" else b"\x00\x01\x02"
            w.add_message(channels[topic], log_time=t, publish_time=t, data=data)
        w.finish()


def test_empty_bag_is_clean(tmp_path):
    p = tmp_path / "empty.mcap"
    write_mcap(p, [])
    assert run(str(p)) == []
    assert bag_start_ns(str(p)) == 0


def test_duplicate_timestamps_do_not_crash(tmp_path):
    # 11 messages at the SAME log_time, then one 5s later. Median gap is 0, so
    # the old code did `gap / 0` -> ZeroDivisionError. Must survive and flag the
    # real gap with ratio == inf.
    msgs = [("/a", 1000, {"i": i}) for i in range(11)]
    msgs.append(("/a", 1000 + 5_000_000_000, {"i": 99}))
    p = tmp_path / "dup.mcap"
    write_mcap(p, msgs)

    dropouts = [e for e in run(str(p)) if e.detector == "dropout"]
    assert len(dropouts) == 1
    assert dropouts[0].details["ratio"] == float("inf")


def test_highrate_missing_frame_not_flagged(tmp_path):
    # 100 Hz topic missing a single frame (0.02s gap) is below the absolute
    # floor and must not be reported.
    t = 1_000_000_000
    msgs = []
    for i in range(60):
        msgs.append(("/fast", t, {"i": i}))
        t += 10_000_000          # 0.01s
        if i == 30:
            t += 10_000_000      # one dropped frame -> 0.02s gap
    p = tmp_path / "fast.mcap"
    write_mcap(p, msgs)
    assert [e for e in run(str(p)) if e.detector == "dropout"] == []


def test_undecodable_encoding_does_not_crash(tmp_path):
    # Non-JSON channel with no decoder -> msg is None; timing detectors still run.
    msgs = [("/x", 1_000_000_000 + i * 100_000_000, {"i": i}) for i in range(12)]
    p = tmp_path / "proto.mcap"
    write_mcap(p, msgs, encoding="protobuf")
    assert isinstance(run(str(p)), list)


def test_uppercase_extension_is_read_as_mcap(tmp_path):
    msgs = [("/a", 1_000_000_000 + i * 100_000_000, {"i": i}) for i in range(12)]
    p = tmp_path / "UP.MCAP"
    write_mcap(p, msgs)
    assert isinstance(run(str(p)), list)


def test_missing_file_exits_cleanly():
    assert main(["run", "/no/such/file.mcap"]) == 2


def test_corrupt_file_exits_cleanly(tmp_path):
    p = tmp_path / "bad.mcap"
    p.write_text("<html>not an mcap</html>")
    assert main(["run", str(p)]) == 1
