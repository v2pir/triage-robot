# robot-triage

Point it at a robot log (`.mcap` or ROS 1 `.bag`) and it flags common-sense
failures automatically, so you can jump straight to the moment things went wrong.

## What it flags

| Detector | Catches |
|---|---|
| **dropout** | a topic that goes silent - sensor drops out mid-run |
| **divergence** | command-vs-actual mismatch (`/cmd_vel` vs `/odom`) - stuck wheel, e-stop |
| **error_burst** | a cluster of error-level logs on `/rosout` |

## Install

```bash
pip install -e .
# optional: decode ROS 2 (cdr) messages inside .mcap
pip install -e '.[ros2]'
```

## Use

```bash
triage run mylog.mcap
```

## How it works

```
reader    -> yields (topic, t, msg) from a bag
detectors -> turn messages into Events
report    -> text for a human
```

`events.Event` is the shared vocabulary. Adding a detector = write a `Detector`
subclass, then list it in `robot_triage/detectors/__init__.py`.
