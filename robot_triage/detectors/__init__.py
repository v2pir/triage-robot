"""Detectors turn a stream of messages into Events.

build_detectors(config) builds the enabled detectors, applying any per-detector
overrides. To add a detector: write the class, then list it in DETECTOR_CLASSES.
"""

import sys

from .base import Detector
from .dropout import DropoutDetector
from .error_burst import ErrorBurstDetector
from .divergence import DivergenceDetector

DETECTOR_CLASSES = {
    cls.name: cls
    for cls in (DropoutDetector, ErrorBurstDetector, DivergenceDetector)
}

ALL_DETECTORS = list(DETECTOR_CLASSES.values())


def build_detectors(config=None):
    config = config or {}
    det_cfg = config.get("detectors", {}) or {}

    for name in det_cfg:
        if name not in DETECTOR_CLASSES:
            print(
                f"triage: warning: config mentions unknown detector '{name}' "
                f"(known: {', '.join(sorted(DETECTOR_CLASSES))})",
                file=sys.stderr,
            )

    instances = []
    for name, cls in DETECTOR_CLASSES.items():
        opts = dict(det_cfg.get(name, {}) or {})
        if opts.pop("enabled", True) is False:
            continue
        opts = _normalize(name, opts)
        try:
            instances.append(cls(**opts))
        except TypeError as exc:
            raise SystemExit(f"triage: bad config for detector '{name}': {exc}")
    return instances


def _normalize(name, opts):
    if name == "range" and "rules" in opts:
        opts["rules"] = [
            (r["topic"], r["field"], r.get("low"), r.get("high"),
             r.get("label", r["topic"]))
            for r in opts["rules"]
        ]
    return opts
