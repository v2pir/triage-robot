"""Error-burst detector: clusters of error-level log messages.

A single error is often noise; a *burst* usually marks the moment something
actually went wrong -- the robot complaining about itself. We watch log topics
(ROS's /rosout uses rcl_interfaces/msg/Log, whose ``level`` field is 40=ERROR,
50=FATAL) and collapse a run of nearby errors into one Event.
"""

from ..events import Event
from ..util import field
from .base import Detector

# rcl_interfaces/msg/Log levels. ERROR and above are worth flagging.
ROS_ERROR_LEVEL = 40


class ErrorBurstDetector(Detector):
    name = "error_burst"

    def __init__(self, log_topics=("/rosout",), window_s=3.0, threshold=5):
        # errors within `window_s` of each other belong to the same burst;
        # a burst needs at least `threshold` errors to report.
        self.log_topics = set(log_topics)
        self.window_s = window_s
        self.threshold = threshold
        self.errors = []  # list of (t, text)

    def process(self, topic, t, msg):
        if topic not in self.log_topics or msg is None:
            return
        level = field(msg, "level")
        if level is None or level < ROS_ERROR_LEVEL:
            return
        text = field(msg, "msg") or field(msg, "message") or ""
        self.errors.append((t, str(text).strip()))

    def finish(self):
        events = []
        burst = []
        for t, text in self.errors:
            if burst and t - burst[-1][0] > self.window_s:
                events.extend(self._flush(burst))
                burst = []
            burst.append((t, text))
        events.extend(self._flush(burst))
        return events

    def _flush(self, burst):
        if len(burst) < self.threshold:
            return []
        t_start, t_end = burst[0][0], burst[-1][0]
        span = t_end - t_start
        sample = next((text for _, text in burst if text), "")
        return [
            Event(
                t_start=t_start,
                t_end=t_end,
                severity="critical",
                detector=self.name,
                summary=(
                    f"{len(burst)} error-level log messages in {span:.2f}s "
                    f"starting at {t_start:.1f}s"
                    + (f' - first: "{sample}"' if sample else "")
                ),
                details={
                    "count": len(burst),
                    "span_seconds": span,
                    "first_message": sample,
                },
            )
        ]
