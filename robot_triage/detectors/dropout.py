from collections import defaultdict
from ..events import Event
from .base import Detector
import statistics

class DropoutDetector(Detector):
    name = "dropout"

    def __init__(self, gap_factor=5.0, min_gap_s=0.5, min_samples=10):
        # A gap must exceed gap_factor x the topic's median interval AND be at
        # least min_gap_s in absolute terms (so a high-rate topic missing one
        # frame doesn't get flagged). Need min_samples to judge a topic at all.
        self.gap_factor = gap_factor
        self.min_gap_s = min_gap_s
        self.min_samples = min_samples
        self.times = defaultdict(list)

    def process(self, topic, t, msg):
        self.times[topic].append(t)

    def finish(self):
        events = []
        for topic, ts in self.times.items():
            if len(ts) < self.min_samples:
                continue
            gaps = [ts[n+1] - ts[n] for n in range(len(ts)-1)]
            normal = statistics.median(gaps)
            # normal can be 0 when >=half the timestamps are identical (batched
            # or duplicate log_time) -- guard the division and fall back to the
            # absolute floor as the only threshold.
            threshold = max(self.gap_factor * normal, self.min_gap_s)
            for i, gap in enumerate(gaps):
                if gap >= threshold:
                    ratio = gap / normal if normal > 0 else float("inf")
                    events.append(
                        Event(
                            t_start = ts[i],
                            t_end = ts[i+1],
                            severity = "warn",
                            detector = self.name,
                            summary = f"{topic} has gone completely silent for {gap:.2f} seconds between timestamps {ts[i]:.1f} and {ts[i+1]:.1f}",
                            details={
                                "topic": topic,
                                "gap_seconds": gap,
                                "normal_gap_seconds": normal,
                                "ratio": ratio,
                                "msg_count": len(ts)
                                }
                        )
                    )
        return events