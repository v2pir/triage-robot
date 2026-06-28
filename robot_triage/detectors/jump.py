"""Jump detector: the robot teleports.

Odometry position should move smoothly. A single step that's wildly larger than
the others usually means a localization glitch, a dropped odometry frame, or a
pose reset -- the robot "jumps" somewhere it couldn't physically have gone. Like
the dropout detector, we learn what a normal step looks like (median) and flag
steps that dwarf it.
"""

import math
import statistics

from ..events import Event
from ..util import field
from .base import Detector


class JumpDetector(Detector):
    name = "jump"

    def __init__(
        self,
        topic="/odom",
        pos_path="pose.pose.position",
        factor=8.0,
        min_jump_m=0.5,
        min_samples=10,
    ):
        self.topic = topic
        self.pos_path = pos_path
        self.factor = factor
        self.min_jump_m = min_jump_m
        self.min_samples = min_samples
        self.last = None   # (x, y, z)
        self.steps = []    # (t, distance)

    def process(self, topic, t, msg):
        if topic != self.topic or msg is None:
            return
        pos = field(msg, self.pos_path)
        if pos is None:
            return
        x = field(pos, "x", 0.0)
        y = field(pos, "y", 0.0)
        z = field(pos, "z", 0.0)
        if self.last is not None:
            self.steps.append((t, math.dist((x, y, z), self.last)))
        self.last = (x, y, z)

    def finish(self):
        dists = [d for _, d in self.steps]
        if len(dists) < self.min_samples:
            return []
        typical = statistics.median(dists)
        threshold = max(self.factor * typical, self.min_jump_m)

        events = []
        for t, d in self.steps:
            if d >= threshold and d >= self.min_jump_m:
                events.append(
                    Event(
                        t_start=t,
                        t_end=t,
                        severity="critical",
                        detector=self.name,
                        summary=(
                            f"{self.topic} position jumped {d:.2f}m in one step at "
                            f"{t:.1f}s (~{typical:.3f}m normal)"
                        ),
                        details={
                            "topic": self.topic,
                            "jump_meters": d,
                            "typical_step_meters": typical,
                        },
                    )
                )
        return events
