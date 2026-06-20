"""Stage 1: open a bag and yield decoded messages.

Yields ``(topic, t_seconds, msg)`` where ``t_seconds`` is relative to the start
of the bag and ``msg`` is the *decoded* message (a dict for JSON channels, a
deserialized object for ROS messages, or ``None`` when we can't decode it --
timing-only detectors like dropout still work in that case).
"""

import json
from pathlib import Path


def _is_mcap(path):
    return Path(path).suffix.lower() == ".mcap"


def read_messages(path):
    """Yield ``(topic, t_seconds, msg)`` for every message, in log order."""
    path = Path(path)
    if _is_mcap(path):
        yield from _read_mcap(path)
    else:
        yield from _read_rosbag(path)


def bag_start_ns(path):
    """Absolute start time of the bag, in nanoseconds since the Unix epoch.

    Needed to turn an Event's bag-relative time back into a wall-clock
    timestamp (e.g. for Foxglove's ``time=`` deep-link parameter).
    """
    path = Path(path)
    if _is_mcap(path):
        from mcap.reader import make_reader

        with open(path, "rb") as f:
            summary = make_reader(f).get_summary()
            stats = getattr(summary, "statistics", None) if summary else None
            if stats and stats.message_start_time:
                return stats.message_start_time
        with open(path, "rb") as f:
            for _schema, _channel, message in make_reader(f).iter_messages():
                return message.log_time
        return 0

    from rosbags.highlevel import AnyReader

    with AnyReader([path]) as reader:
        return reader.start_time


# --------------------------------------------------------------------------- #
# MCAP
# --------------------------------------------------------------------------- #

def _read_mcap(path):
    from mcap.reader import make_reader

    factory = _ros2_decoder_factory()
    decoders = {}  # channel.id -> decoder callable (or False if undecodable)

    with open(path, "rb") as f:
        reader = make_reader(f)
        t0 = None
        for schema, channel, message in reader.iter_messages():
            if t0 is None:
                t0 = message.log_time
            t = (message.log_time - t0) / 1e9
            msg = _decode_mcap(channel, schema, message, factory, decoders)
            yield channel.topic, t, msg


def _decode_mcap(channel, schema, message, factory, decoders):
    if channel.message_encoding == "json":
        try:
            return json.loads(message.data)
        except Exception:
            return None

    # ROS 2 (cdr) channels need mcap-ros2-support; decode lazily per channel.
    if factory is not None:
        decoder = decoders.get(channel.id)
        if decoder is None:
            try:
                decoder = factory.decoder_for(channel.message_encoding, schema)
            except Exception:
                decoder = False
            decoders[channel.id] = decoder or False
        if decoder:
            try:
                return decoder(message.data)
            except Exception:
                return None
    return None


def _ros2_decoder_factory():
    try:
        from mcap_ros2.decoder import DecoderFactory

        return DecoderFactory()
    except ImportError:
        return None


# --------------------------------------------------------------------------- #
# ROS 1 / ROS 2 bags (via rosbags)
# --------------------------------------------------------------------------- #

def _read_rosbag(path):
    from rosbags.highlevel import AnyReader

    with AnyReader([path]) as reader:
        t0 = None
        for conn, timestamp, rawdata in reader.messages():
            if t0 is None:
                t0 = timestamp
            t = (timestamp - t0) / 1e9
            try:
                msg = reader.deserialize(rawdata, conn.msgtype)
            except Exception:
                msg = None
            yield conn.topic, t, msg
