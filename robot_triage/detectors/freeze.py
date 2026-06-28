"""Freeze detector: a topic keeps publishing, but the value stops changing.

Messages keep arriving at the normal rate (so dropout won't fire) but the payload
is stuck - a camera returning the same frame, an encoder wedged at one count. We
flag a long run of byte-identical messages, but only on a topic that takes more
than one value elsewhere, so latched/constant topics don't get flagged.
"""

import json

from ..events import Event
from .base import Detector


def _signature(msg):
    """A hashable/comparable fingerprint of a decoded message."""
    try:
        if isinstance(msg, dict):
            return json.dumps(msg, sort_keys=True, default=str)
        return repr(msg)
    except Exception:
        return None


class FreezeDetector(Detector):
    name = "freeze"

    def __init__(
        self,
        min_freeze_s=2.0,
        min_count=10,
        ignore_topics=("/rosout", "/tf_static", "/clock"),
    ):
        self.min_freeze_s = min_freeze_s
        self.min_count = min_count
        self.ignore = set(ignore_topics)
        self.state = {}     # topic -> current run {sig, t_start, t_last, count}
        self.distinct = {}  # topic -> set of signatures (capped)
        self.frozen = []    # qualifying runs: (topic, t_start, t_last, count)

    def process(self, topic, t, msg):
        if topic in self.ignore or msg is None:
            return
        sig = _signature(msg)
        if sig is None:
            return

        seen = self.distinct.setdefault(topic, set())
        if len(seen) < 3:
            seen.add(sig)

        run = self.state.get(topic)
        if run and run["sig"] == sig:
            run["t_last"] = t
            run["count"] += 1
        else:
            if run:
                self._close(topic, run)
            self.state[topic] = {"sig": sig, "t_start": t, "t_last": t, "count": 1}

    def _close(self, topic, run):
        duration = run["t_last"] - run["t_start"]
        if duration >= self.min_freeze_s and run["count"] >= self.min_count:
            self.frozen.append((topic, run["t_start"], run["t_last"], run["count"]))

    def finish(self):
        for topic, run in self.state.items():
            self._close(topic, run)

        events = []
        for topic, t_start, t_last, count in self.frozen:
            # Only a freeze if the topic varies elsewhere -- otherwise it's just
            # a constant-by-design topic.
            if len(self.distinct.get(topic, ())) > 1:
                duration = t_last - t_start
                events.append(
                    Event(
                        t_start=t_start,
                        t_end=t_last,
                        severity="warn",
                        detector=self.name,
                        summary=(
                            f"{topic} value frozen for {duration:.2f}s "
                            f"({count} identical messages) starting at {t_start:.1f}s"
                        ),
                        details={
                            "topic": topic,
                            "duration_seconds": duration,
                            "identical_messages": count,
                        },
                    )
                )
        return events
