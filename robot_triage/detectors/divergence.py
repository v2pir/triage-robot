"""Command-vs-actual divergence: the robot isn't doing what it was told.

Compares commanded velocity (/cmd_vel) against measured velocity (/odom). A
sustained mismatch usually means a stuck wheel, an e-stop, or a controller
fighting itself. We only check an axis while it's actually being commanded
(|cmd| > min_cmd), so a robot that's meant to be stopped doesn't get flagged.
"""

from ..events import Event
from ..util import field
from .base import Detector

# (label, path-in-cmd, path-in-odom, min-commanded-magnitude, abs-tolerance)
DEFAULT_AXES = (
    ("linear.x", "linear.x", "twist.twist.linear.x", 0.05, 0.15),
    ("angular.z", "angular.z", "twist.twist.angular.z", 0.10, 0.20),
)


class DivergenceDetector(Detector):
    name = "divergence"

    def __init__(
        self,
        cmd_topic="/cmd_vel",
        actual_topic="/odom",
        axes=DEFAULT_AXES,
        min_duration_s=0.75,
        max_cmd_age_s=1.0,
    ):
        self.cmd_topic = cmd_topic
        self.actual_topic = actual_topic
        self.axes = axes
        self.min_duration_s = min_duration_s
        self.max_cmd_age_s = max_cmd_age_s

        self.last_cmd = None       # decoded /cmd_vel message
        self.last_cmd_t = None
        # per-axis active divergence run: {"t_start", "t_last", "peak"}
        self.runs = {label: None for (label, *_ ) in axes}
        self.events = []

    def process(self, topic, t, msg):
        if topic == self.cmd_topic:
            self.last_cmd = msg
            self.last_cmd_t = t
        elif topic == self.actual_topic:
            self._compare(t, msg)

    def _compare(self, t, odom):
        # Ignore odometry that has no recent command to compare against.
        if self.last_cmd is None or (t - self.last_cmd_t) > self.max_cmd_age_s:
            for label in self.runs:
                self._end_run(label)
            return

        for label, cmd_path, act_path, min_cmd, tol in self.axes:
            cmd = field(self.last_cmd, cmd_path)
            act = field(odom, act_path)
            if cmd is None or act is None:
                continue
            diverging = abs(cmd) > min_cmd and abs(cmd - act) > tol
            if diverging:
                run = self.runs[label]
                err = abs(cmd - act)
                if run is None:
                    self.runs[label] = {"t_start": t, "t_last": t,
                                        "peak": err, "cmd": cmd, "act": act}
                else:
                    run["t_last"] = t
                    if err > run["peak"]:
                        run["peak"] = err
                        run["cmd"] = cmd
                        run["act"] = act
            else:
                self._end_run(label)

    def _end_run(self, label):
        run = self.runs[label]
        if run is None:
            return
        self.runs[label] = None
        duration = run["t_last"] - run["t_start"]
        if duration < self.min_duration_s:
            return
        self.events.append(
            Event(
                t_start=run["t_start"],
                t_end=run["t_last"],
                severity="critical",
                detector=self.name,
                summary=(
                    f"commanded {label} {run['cmd']:.2f} but actual ~{run['act']:.2f} "
                    f"for {duration:.2f}s at {run['t_start']:.1f}s"
                ),
                details={
                    "axis": label,
                    "commanded": run["cmd"],
                    "actual": run["act"],
                    "peak_error": run["peak"],
                    "duration_seconds": duration,
                },
            )
        )

    def finish(self):
        for label in list(self.runs):
            self._end_run(label)
        return self.events
