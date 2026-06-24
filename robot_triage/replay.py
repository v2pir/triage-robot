"""Replay: cut a short, self-contained .mcap around each flagged moment.

A clip you can drag straight into Foxglove (or any viewer) is the reliable half
of "one-click replay" -- it always works offline, no deep-link guesswork.

Events carry times relative to the bag start, so we recover the bag's absolute
start time and slice ``[t_start - pad, t_end + pad]`` out of the original file,
copying every topic so the moment still has full context.

All clips are cut in a **single pass** over the source: we open one writer per
event and, for each message read, copy it into every clip whose window contains
it. That makes cost O(filesize) instead of O(events x filesize) -- decompressing
a multi-GB bag once instead of once per event.
"""

import os
from pathlib import Path

from .reader import bag_start_ns


def extract_clips(bag_path, events, out_dir="clips", pad_s=3.0):
    """Write one .mcap per event into ``out_dir``. Returns the paths written."""
    path = Path(bag_path)
    if path.suffix.lower() != ".mcap":
        print(f"  (clip extraction supports .mcap only for now; skipping {path.name})")
        return []
    if not events:
        return []

    os.makedirs(out_dir, exist_ok=True)
    t0 = bag_start_ns(path)

    clips = []
    for i, e in enumerate(events):
        stem = f"{i:02d}_{e.detector}_{e.t_start:.1f}s".replace("/", "_")
        clips.append({
            "lo": t0 + int((e.t_start - pad_s) * 1e9),
            "hi": t0 + int((e.t_end + pad_s) * 1e9),
            "dst": os.path.join(out_dir, stem + ".mcap"),
        })

    _write_clips(path, clips)
    return [c["dst"] for c in clips]


def _write_clips(src, clips):
    from mcap.reader import make_reader
    from mcap.writer import Writer

    writers = []
    handles = []
    try:
        for c in clips:
            fh = open(c["dst"], "wb")
            w = Writer(fh)
            w.start()
            handles.append(fh)
            writers.append({
                "w": w, "lo": c["lo"], "hi": c["hi"],
                "schema_ids": {}, "channel_ids": {},
            })

        with open(src, "rb") as f:
            for schema, channel, message in make_reader(f).iter_messages():
                lt = message.log_time
                for wr in writers:
                    if wr["lo"] <= lt <= wr["hi"]:
                        _copy_message(wr, schema, channel, message)

        for wr in writers:
            wr["w"].finish()
    finally:
        for fh in handles:
            fh.close()


def _copy_message(wr, schema, channel, message):
    w = wr["w"]
    if schema is not None and schema.id not in wr["schema_ids"]:
        wr["schema_ids"][schema.id] = w.register_schema(
            name=schema.name, encoding=schema.encoding, data=schema.data
        )
    if channel.id not in wr["channel_ids"]:
        new_schema_id = wr["schema_ids"].get(schema.id, 0) if schema else 0
        wr["channel_ids"][channel.id] = w.register_channel(
            topic=channel.topic,
            message_encoding=channel.message_encoding,
            schema_id=new_schema_id,
        )
    w.add_message(
        channel_id=wr["channel_ids"][channel.id],
        log_time=message.log_time,
        data=message.data,
        publish_time=message.publish_time,
        sequence=message.sequence,
    )
