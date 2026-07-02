"""Load a triage config (YAML or JSON) that remaps topics and tunes detectors.

The whole point: default topic names (``/odom``, ``/cmd_vel``, ...) rarely match
a real robot, so a clean report on an unconfigured bag can be a false all-clear.
A config points each detector at the right topics for *your* robot.

Shape (every key optional; omitted detectors run with defaults, `enabled: false`
turns one off):

    detectors:
      dropout:     {min_gap_s: 1.0}
      divergence:  {cmd_topic: /robot/cmd_vel, actual_topic: /robot/odom}
      jump:        {topic: /camera/odom/sample, min_jump_m: 0.3}
      freeze:      {ignore_topics: [/rosout, /tf_static]}
      error_burst: {log_topics: [/rosout, /diagnostics], threshold: 3}
      range:
        rules:
          - {topic: /battery, field: voltage, low: 10.0, high: 16.0, label: battery V}
"""

import json
from pathlib import Path


def load_config(path):
    """Parse a config file into a dict. Returns {} for no path / empty file."""
    if not path:
        return {}
    p = Path(path)
    text = p.read_text()
    if not text.strip():
        return {}

    try:
        import yaml

        data = yaml.safe_load(text)
    except ImportError:
        # PyYAML is a declared dependency, but degrade gracefully to JSON.
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"triage: reading YAML config needs PyYAML (pip install pyyaml); "
                f"parsing {p} as JSON failed: {exc}"
            )

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SystemExit(f"triage: config {p} must be a mapping at the top level")
    return data
