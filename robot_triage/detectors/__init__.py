"""Stage 2: detectors turn a stream of messages into Events.

``build_detectors(config)`` instantiates the enabled detectors, applying any
per-detector overrides from the config. Adding a detector is two steps: write
the class, then list it in ``DETECTOR_CLASSES`` below.
"""

import sys

from .base import Detector
from .dropout import DropoutDetector
from .error_burst import ErrorBurstDetector
from .divergence import DivergenceDetector
from .freeze import FreezeDetector
from .jump import JumpDetector
from .range_check import RangeDetector

# name -> class, keyed by each detector's `.name`.
DETECTOR_CLASSES = {
    cls.name: cls
    for cls in (
        DropoutDetector,
        ErrorBurstDetector,
        DivergenceDetector,
        FreezeDetector,
        JumpDetector,
        RangeDetector,
    )
}

# Back-compat: the plain list of default factories.
ALL_DETECTORS = list(DETECTOR_CLASSES.values())


def build_detectors(config=None):
    """Return detector instances, applying overrides from ``config``.

    ``config`` is the parsed config dict (see triage.config). Its ``detectors``
    mapping keys each detector by name; ``enabled: false`` skips one, and the
    remaining keys are passed to the detector's constructor.
    """
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
    """Adapt config-friendly shapes to what a constructor expects."""
    if name == "range" and "rules" in opts:
        opts["rules"] = [
            (r["topic"], r["field"], r.get("low"), r.get("high"),
             r.get("label", r["topic"]))
            for r in opts["rules"]
        ]
    return opts


__all__ = [
    "Detector",
    "DropoutDetector",
    "ErrorBurstDetector",
    "DivergenceDetector",
    "FreezeDetector",
    "JumpDetector",
    "RangeDetector",
    "DETECTOR_CLASSES",
    "ALL_DETECTORS",
    "build_detectors",
]
