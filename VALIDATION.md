# Validation

## Synthetic bag (`make_test_bag.py`)

`python make_test_bag.py` writes a 60s `test.mcap` with one planted failure per
detector. `triage run test.mcap` flags all six, at the right times:

| detector | planted | flagged |
|---|---|---|
| range | /battery_state 140% at 10s | `battery % above range: 1.4 ... at 10.0s` |
| dropout | /camera silent 20-25s | `/camera silent for 5.10s ... 19.9 and 25.0` |
| jump | /odom +5m teleport at 30s | `position jumped 5.05m ... at 30.0s` |
| divergence | /cmd_vel 0.5 vs /odom ~0, 40-43s | `commanded linear.x 0.50 but actual ~0.02 ... 40.0s` |
| error_burst | /rosout ERRORs 41-42s | `10 error-level log messages ... 41.0s` |
| freeze | /imu stuck 50-53s | `/imu value frozen for 2.90s ... 50.0s` |

## Real data (`race_1.bag`)

A real RealSense T265 recording (587 MB, not committed): 28.4s of genuine VIO
odometry on `/camera/odom/sample` (`nav_msgs/Odometry`, 5679 samples @ ~200 Hz),
plus `/camera/imu` and `/camera/fisheye2/image_raw`. This exercises the ROS 1
`.bag` reader path and message deserialization on real data.

Running the odometry detectors against it:

- **freeze: 0 events** - no false positives on genuinely noisy real odometry.
- **jump: 3 events** - median single-step displacement is 0.053 m; these three
  steps reach ~0.97 m (**~18× the median**) inside a single 5 ms sample, i.e. an
  implied ~190 m/s. That's physically impossible for the platform and consistent
  with VIO tracking loss - the detector surfaced real glitches, not planted ones.

Note: on a genuinely high-dynamics platform the jump threshold (`factor=8`) may
need tuning; flagging it here is honest signal, not a silent pass.

### Still validated on synthetic only

**divergence** needs a topic pair like `/cmd_vel` + `/odom`. No free single-file
public bag with both was available; `race_1.bag` has odometry but no commands.
To validate on your own robot:

```bash
ros2 bag record -s mcap /cmd_vel /odom     # drive it around, then:
triage run rosbag2_*/  # or the .mcap inside
```
