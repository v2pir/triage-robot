# robot-triage

[![PyPI](https://img.shields.io/pypi/v/robot-triage)](https://pypi.org/project/robot-triage/)
[![Python](https://img.shields.io/pypi/pyversions/robot-triage)](https://pypi.org/project/robot-triage/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Point it at a robot log (`.mcap` or ROS 1 `.bag`) and it flags the common-sense
failures automatically - then makes each flagged moment replayable in one click.

## What it flags

| Detector | Catches |
|---|---|
| **dropout** | a topic that goes silent - sensor drops out mid-run |
| **divergence** | command-vs-actual mismatch (`/cmd_vel` says drive, `/odom` says no) - stuck wheel, e-stop, controller fighting itself |
| **error_burst** | a cluster of error-level logs on `/rosout` - the robot complaining about itself |
| **freeze** | a topic still publishing but the value stopped changing - wedged sensor / stale frame |
| **jump** | odometry position teleports - localization glitch, dropped frame, pose reset |
| **range** | a value leaves its sane envelope or goes NaN/Inf - glitchy telemetry (rules configurable) |

See [`BACKLOG.md`](BACKLOG.md) for the next detectors, prioritized from real Foxglove/ROS issue-tracker complaints.

## Install

```bash
pip install robot-triage
# optional: decode ROS 2 (cdr) messages inside .mcap
pip install 'robot-triage[ros2]'
```

From source:

```bash
git clone https://github.com/v2pir/triage-robot && cd triage-robot
pip install -e .
```

## Use

```bash
triage run mylog.mcap                          # scan + print flagged moments
triage run mylog.mcap --clips                  # + cut a .mcap clip per moment
triage run mylog.mcap --html report.html       # + a pretty clickable report
triage run mylog.mcap --html report.html --bag-url https://host/mylog.mcap
triage run mylog.mcap --config myrobot.yaml    # remap topics / tune thresholds
```

## Configure it for your robot (important)

The content detectors default to conventional topic names (`/odom`, `/cmd_vel`,
`/rosout`, `/battery_state`). **Real robots namespace their topics**, so on an
unconfigured bag a clean report can be a false all-clear. Point each detector at
your robot's real topics with `--config` (see [`triage.example.yaml`](triage.example.yaml)):

```yaml
detectors:
  jump:        {topic: /camera/odom/sample, min_jump_m: 0.3}
  divergence:  {enabled: false}          # no /cmd_vel in this bag
  error_burst: {log_topics: [/rosout, /diagnostics]}
```

Example - the same real bag, before vs. after config:

```
$ triage run race_1.bag                       # jump watches /odom (absent)
No issues detected.
$ triage run race_1.bag --config race.yaml     # jump -> /camera/odom/sample
[CRITICAL] jump: /camera/odom/sample position jumped 0.97m in one step at 23.1s
```

## One-click replay

Every flagged moment gives you two ways back into the data:

- **Clip** - a short `.mcap` (`±3s`) cut around the moment (`--clips`). Drag it
  into Foxglove, RViz, anything. Always works, offline.
- **Open in Foxglove** - a deep link that seeks Foxglove's playhead to the exact
  instant. Needs the bag reachable at an HTTP URL, so pass `--bag-url`.

## Architecture

```
reader   -> yields (topic, t, msg) from a bag        (Stage 1)
detectors-> turn messages into Events                (Stage 2)
report   -> text / html for a human                  (Stage 3/4)
replay   -> cut a clip around each Event
```

`events.Event` is the shared vocabulary. Adding a detector = write a
`Detector` subclass, then list it in `robot_triage/detectors/__init__.py`.

## Make a test bag

```bash
python make_test_bag.py     # writes test.mcap with one planted failure per detector
triage run test.mcap --clips --html report.html
```
