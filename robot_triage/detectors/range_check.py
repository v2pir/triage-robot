"""Range detector: a value leaves its sane bounds (or goes NaN/Inf).

Checks configured (topic, field, low, high) rules and flags a sustained excursion,
so a single noisy sample doesn't trip it. NaN/Inf are always flagged. Pass your
own rules for your robot's telemetry; the defaults only fire if the topic exists.
"""

import math

from ..events import Event
from ..util import field
from .base import Detector

# (topic, field_path, low, high, label). low/high may be None for one-sided.
DEFAULT_RULES = (
    ("/battery_state", "percentage", 0.0, 1.0, "battery %"),
)


class RangeDetector(Detector):
    name = "range"

    def __init__(self, rules=DEFAULT_RULES, min_duration_s=0.4):
        self.rules = list(rules)
        self.min_duration_s = min_duration_s
        self.runs = {}      # rule index -> {t_start, t_last, worst, reason}
        self.events = []

    def process(self, topic, t, msg):
        if msg is None:
            return
        for i, (rtopic, path, low, high, _label) in enumerate(self.rules):
            if topic != rtopic:
                continue
            raw = field(msg, path)
            if raw is None:
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue

            if math.isnan(v) or math.isinf(v):
                reason, worst = "NaN/Inf", v
            elif low is not None and v < low:
                reason, worst = "below", v
            elif high is not None and v > high:
                reason, worst = "above", v
            else:
                self._close(i)
                continue

            run = self.runs.get(i)
            if run is None:
                self.runs[i] = {"t_start": t, "t_last": t, "worst": worst, "reason": reason}
            else:
                run["t_last"] = t
                if _is_worse(reason, worst, run["worst"]):
                    run["worst"] = worst

    def _close(self, i):
        run = self.runs.pop(i, None)
        if not run:
            return
        duration = run["t_last"] - run["t_start"]
        if duration < self.min_duration_s:
            return
        topic, path, low, high, label = self.rules[i]
        self.events.append(
            Event(
                t_start=run["t_start"],
                t_end=run["t_last"],
                severity="warn",
                detector=self.name,
                summary=(
                    f"{label} {run['reason']} range: {run['worst']:.3g} "
                    f"(allowed [{low}, {high}]) for {duration:.2f}s at {run['t_start']:.1f}s"
                ),
                details={
                    "topic": topic,
                    "field": path,
                    "worst_value": run["worst"],
                    "low": low,
                    "high": high,
                    "duration_seconds": duration,
                },
            )
        )

    def finish(self):
        for i in list(self.runs):
            self._close(i)
        return self.events


def _is_worse(reason, candidate, current):
    if reason == "NaN/Inf":
        return True
    if reason == "above":
        return candidate > current
    if reason == "below":
        return candidate < current
    return False
