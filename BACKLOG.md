# Detector backlog

This backlog was built by mining real, specific complaints from robotics engineers across GitHub issue trackers (`ros2/*`, `ros-navigation/navigation2`, `ros/geometry2`, `ros-controls/ros2_control`, `ros-perception/*`, `cra-ros-pkg/robot_localization`, `foxglove/*`), ROS Discourse, ROS Answers, and Robotics Stack Exchange. We searched the terms the user hits when a robot misbehaves ("time went backwards", "extrapolation into the future", "incompatible QoS", "TF_REPEATED_DATA", "nan inf laser scan", "odom jump teleport", "missed deadline", etc.), then kept only failures that (a) show up repeatedly across independent threads and (b) are inferable from a decoded `(topic, time, msg)` stream in an `.mcap` / ROS bag. Each detector below cites the actual issue/post that motivates it. Priorities weigh *how common + how painful + how cheap to detect*: **P0** = frequent, high-severity, cheap; **P1** = important but narrower or costlier; **P2** = valuable polish or context-hungry. A cross-cutting design note recurs throughout: a log carries **two independent timelines** - the recorder's `log_time` (receive time) and the message's `header.stamp` (source time) - and neither is trustworthy, so many detectors are facets of reconciling those two clocks.

## Priority table

| # | Detector | Flags | Key signal | Difficulty | Priority |
|---|----------|-------|-----------|-----------|----------|
| 1 | Clock reversal | Effective time moves backwards (`/clock` or per-topic stamp/log_time decreases) | `/clock` + per-topic time monotonicity | Easy | **P0** |
| 2 | Zero / uninitialized stamp | Header-bearing msgs with `stamp == 0` | `header.stamp.{sec,nanosec}` | Easy | **P0** |
| 3 | Non-finite sensor data | NaN/Inf in scan / cloud / IMU / odom fields | `ranges[]`, PointCloud2 `data[]`, `orientation.*`, covariance | Easy-Med | **P0** |
| 4 | TF extrapolation / clock skew | Frames stamped seconds apart or lagging query horizon | `/tf` `header.stamp` per frame, cross-frame deltas | Easy-Med | **P0** |
| 5 | Frozen / stuck sensor | Topic keeps publishing but payload is byte-identical | payload hash + `header.stamp` advance | Medium | **P0** |
| 6 | Topic-rate brownout | Sustained rate collapse (e.g. 30 Hz → 5 Hz), not full dropout | per-topic period vs. baseline/expected | Easy | **P0** |
| 7 | QoS reliability mismatch | Sensor topic offered BEST_EFFORT to reliable-defaulting consumers | channel QoS metadata | Easy | **P1** |
| 8 | tf_static latch loss | `/tf_static` recorded VOLATILE / empty offered-QoS → dropped | channel durability metadata, `/tf_static` count | Easy | **P1** |
| 9 | Conflicting TF authority | A child frame with >1 parent / reparenting / divergent duplicate edges | `/tf` edge graph, per-child parent cardinality | Medium | **P1** |
| 10 | Pose / odom teleport | Position/yaw jump larger than dt·v_max; map→odom step | `pose.pose.position`, quaternion→yaw deltas | Medium | **P1** |
| 11 | Diagnostics regression | `/diagnostics` status rising to WARN/ERROR/STALE | `DiagnosticArray.status[].level` | Easy | **P1** |
| 12 | Control-loop overrun | ros2_control misses its update rate / missed cycles | `ControllerUpdateStats`, rosout "Overrun detected" | Easy-Med | **P1** |
| 13 | Node death / lifecycle wedge | Managed node loses bond heartbeat or stalls mid-transition | `/bond`, `TransitionEvent`, rosout silence→respawn | Medium | **P1** |
| 14 | Out-of-order / skewed stamps | Non-monotonic `header.stamp`; `header.stamp` far from `log_time` | per-topic stamp order, `log_time − stamp` | Easy-Med | **P2** |
| 15 | Estimator covariance sanity | IMU sentinel covariance (`-1`/all-zero); EKF covariance blow-up | `*_covariance[]`, `pose.covariance` diagonal trend | Easy-Med | **P2** |

---

## P0 detectors

### 1. Clock reversal ("time went backwards")
**Flags:** the effective clock decreasing - either `/clock` values under `use_sim_time`, or a topic's log_time/stamp stepping backwards. tf2 reacts by dumping its buffer, which breaks every stateful node downstream.

**Real pain:** tf2 prints *"Detected jump back in time of X s. Clearing TF buffer."* which one reporter says "caused all nodes relying on TF information to break"; the root cause is "the clock is switching from real to simulated so the timestamp is jumping," and it recurs on every bag loop. A 2025 ROS 2 user resorted to writing an `/adjusted_clock` monotonic republisher as a workaround. A related rclcpp bug shows a backwards jump hangs `Clock::sleep_for` outright.
- https://github.com/ros/geometry2/issues/463
- https://github.com/ros/geometry2/issues/347
- https://github.com/introlab/rtabmap_ros/issues/1290
- https://github.com/ros2/rclcpp/issues/2383
- https://answers.ros.org/question/346376/ (gmapping "Detected jump back in time… Clearing TF buffer")

**Signal:** monotonicity of `/clock`; per-topic monotonicity of log_time; flag any negative delta beyond a small epsilon.
**Difficulty:** Easy (scan a time series for decreases).
**Why P0:** universally recognized, trivially detectable, and the single most catastrophic clock failure.

### 2. Zero / uninitialized `header.stamp`
**Flags:** Header-bearing messages whose `stamp` is `0` (both `sec` and `nanosec` zero). ROS does not stamp messages automatically, so a publisher that forgets silently poisons every `tf::MessageFilter` / SLAM consumer, which drops the data without a word.

**Real pain:** recurring across a decade - "Time stamps in header message is always 0" because "the code that publishes the message has to set the timestamp." Also seen when messages are published before `/clock` arrives under sim time (recorded with timestamp 0), and in RealSense driver reports.
- https://answers.ros.org/question/327077/ ("Time stamps in header message is always 0")
- https://answers.ros.org/question/123096/ (rosbag C++: header stamp always zero)
- https://github.com/ros2/rosbag2/issues/1276 (msgs before `/clock` recorded with stamp 0)
- https://github.com/IntelRealSense/librealsense/issues/5067

**Signal:** `header.stamp.sec == 0 && header.stamp.nanosec == 0` on Header-bearing topics; special-case the leading pre-`/clock` window in sim-time bags to avoid a benign burst at t=0.
**Difficulty:** Easy.
**Why P0:** one-field check, extremely common, and the downstream failure is silent (data dropped, no error), so it is exactly what a triage tool should surface.

### 3. Non-finite sensor data (NaN / Inf)
**Flags:** NaN/Inf in `LaserScan.ranges[]`, PointCloud2 `x/y/z`, IMU, or odometry fields. Downstream PCL/costmap code assumes these are already gone and crashes when they are not.

**Real pain:**
- perception_pcl maintainer: "all the filters assume nans to be gone"; feeding NaN triggers `Assertion 'isFinite (query)… ' failed. Aborted (core dumped)`. - https://github.com/ros-perception/perception_pcl/issues/164
- LIO-SAM dies with `Point cloud is not in dense format, please remove NaN points first!` - https://github.com/TixiaoShan/LIO-SAM/issues/175
- Nav2 costmap **segfault** from bad scan geometry, "reproduced in sim on two worlds AND on a physical robot," marked in-progress. - https://github.com/ros-navigation/navigation2/issues/2835
- The `is_dense=true` "lie" gotcha (flag says no NaNs, data has them). - https://github.com/PointCloudLibrary/pcl/issues/2870

**Signal:** finiteness scan of `ranges[]` and decoded PointCloud2 `x/y/z` (respecting `point_step`/field layout); cross-check `is_dense` against actual NaN presence; distinguish legitimate `Inf` (no-return in a scan) from `NaN`.
**Difficulty:** Easy for scans; Medium for PointCloud2 (must decode the field layout).
**Why P0:** documented crash/segfault path, and very common with depth/stereo/ultrasonic sources.

### 4. TF extrapolation / clock skew
**Flags:** frames whose stamps are seconds apart (one node not on the shared clock), or whose newest stamp lags a lookup horizon - the "Lookup would require extrapolation into the future/past" family that puts navigation into endless recovery.

**Real pain:** the canonical smoking gun - *"Lookup would require extrapolation into the future. Requested time 1691424773.21 but the latest data is at time 3617.60"* (wall-clock epoch vs. sim seconds), among the most-hit Nav2 issue categories.
- https://github.com/ros-navigation/navigation2/issues/3746
- https://github.com/ros-navigation/navigation2/issues/3101
- https://github.com/ros-navigation/navigation2/issues/3769
- https://answers.ros.org/question/357836/

**Signal:** per `/tf` message compare `header.stamp` to log/receive time and to other frames' newest stamps; flag frames whose stamps sit in a different epoch band, or lag the rest of the tree by seconds. Massive absolute gaps (1.7e9 vs. small sim seconds) are the giveaway.
**Difficulty:** Easy-Medium.
**Why P0:** the most common TF failure engineers ask about, and cheaply inferred from `/tf` alone.

### 5. Frozen / stuck sensor
**Flags:** a topic that keeps publishing while its payload is byte-identical across N consecutive messages (or whose `header.stamp` stops advancing while messages keep arriving) - the robot is acting on a stale world model. Not caught by dropout (messages still flow) or NaN checks (values look valid).

**Real pain:** classic field failure - `ros2 topic echo /scan` shows fresh messages but the data is effectively stale; root causes include a LIDAR timestamped 100 ms late so downstream treats it as obsolete, a driver hardware timeout (`SL_RESULT_OPERATION_TIMEOUT`) leaving the last buffer lingering, and joint velocities that read zero while the joint is moving.
- https://answers.ros.org/question/393581/ (stale LIDAR stamp vs. TF cache)
- https://github.com/Slamtec/rplidar_ros/issues/138 (driver timeout)
- https://github.com/moveit/moveit2_tutorials/issues/333 (velocities always 0 while moving)

**Signal:** hash `ranges[]`/`data[]` (or key fields) and compare across consecutive messages per topic; separately watch for `header.stamp` not advancing while `log_time` does.
**Difficulty:** Medium (per-topic state: last payload hash + last stamp).
**Why P0:** silent and dangerous - the robot keeps driving on frozen perception, and nothing else in the stack complains.

### 6. Topic-rate brownout
**Flags:** a topic whose rate sustains a large drop below its expected/declared value (e.g. a 30 Hz camera collapsing to ~5 Hz) - degradation short of full dropout, which the existing dropout detector misses.

**Real pain:**
- rclpy image republisher "publishing decrease from 30hz to 5hz," reproduced on both Fast-RTPS and CycloneDDS (open). - https://github.com/ros2/rclpy/issues/630
- ZED wrapper: "publish framerate of 30 Hz, however… around 5-7 Hz." - https://community.stereolabs.com/t/zed-2i-low-topic-frequency-with-ros2-wrapper/9761

**Signal:** message count / duration → mean period per topic; compare to an expected Hz or to the topic's own early-window baseline; alert on sustained deviation (distinct from a momentary gap).
**Difficulty:** Easy (receive timestamps are directly in the log).
**Why P0:** extremely common perf complaint, directly measured from the log, and it silently starves controllers/perception without ever going fully silent.

---

## P1 detectors

### 7. QoS reliability mismatch (risk flag)
**Flags:** sensor topics recorded with BEST_EFFORT reliability whose typical consumers (Nav2, RViz, calibration) default to RELIABLE - the #1 "I subscribed and got nothing" cause.

**Real pain:** *"New publisher discovered on topic '/camera/depth/color/points', offering incompatible QoS. No messages will be sent to it. Last incompatible policy: RELIABILITY_QOS_POLICY."* Repeated across camera, scan, and pointcloud threads.
- https://github.com/ros-perception/image_pipeline/issues/827
- https://github.com/ros-perception/image_pipeline/issues/770
- https://github.com/ros2/rviz/issues/1122 (`/scan` "requesting incompatible QoS")
- https://answers.ros.org/question/392676/ (Nav2 `/scan` incompatible QoS)

**Signal:** reliability field in the mcap channel metadata (the *offered* profile) vs. a small table of known consumer defaults.
**Log-inferability:** partial - the bag stores the offered profile but not a live subscriber's requested profile, so this is a heuristic risk flag ("this topic offers best_effort; reliable subs downstream will get nothing"), not a confirmed negotiation failure.
**Difficulty:** Easy (read channel metadata).
**Why P1:** the most common QoS failure in the field, but the log can only flag risk, not confirm the drop.

### 8. tf_static durability / latch loss
**Flags:** latched topics - especially `/tf_static` and maps - recorded with VOLATILE durability or an empty `offered_qos_profiles`, meaning the static transforms were silently dropped from the bag.

**Real pain:** *"if the publisher offers TRANSIENT_LOCAL durability, such as previously published /tf_static messages will be dropped due to the subscriber's compatible request for VOLATILE durability… the offered_qos_profiles field in the resulting bag's metadata.yaml will be an empty string."* Downstream symptom: "rviz2 won't accept my tf_static message from bag."
- https://github.com/ros2/rosbag2/issues/967
- https://github.com/ros2/rviz/issues/916

**Signal:** durability field in channel metadata; empty offered-QoS string; count of `/tf_static` messages (expect ≥1, latched).
**Log-inferability:** strong - this is literally recorded in bag metadata and is a known rosbag2 corruption pattern.
**Difficulty:** Easy.
**Why P1:** silent, breaks TF/playback constantly, and cleanly detectable - a strong candidate to promote to P0 if the tool sees many rosbag2-recorded logs.

### 9. Conflicting TF authority (multi-parent / reparenting)
**Flags:** a `child_frame_id` that appears with more than one distinct parent, or the same edge published by multiple sources with diverging translation/rotation - a tf2 invariant violation that makes a frame visibly "jump."

**Real pain:** frames jump when two authorities publish the same child (e.g. `map→odom` and `world→odom`), and "the usual methods for debugging the tf tree don't help." Long-standing geometry2 feature request; recurring in multi-robot setups.
- https://answers.ros.org/question/341845/ (multiple parents)
- https://github.com/ros/geometry2/issues/437
- https://discourse.openrobotics.org/t/tf-tree-in-a-multi-robot-setup-in-ros2/41426

**Signal:** build the frame graph from `/tf` + `/tf_static`; flag any child with parent-cardinality > 1, or the same edge published at overlapping stamps with divergent values.
**Difficulty:** Medium.
**Why P1:** directly causes silent localization jumps and is hard to eyeball, but rarer than the extrapolation family.

### 10. Pose / odom teleport
**Flags:** a single-step jump in position or yaw larger than physically achievable given `dt` and a plausible max velocity, and discrete `map→odom` steps that corrupt the costmap.

**Real pain:** "AMCL: cannot match well, jumps crazily" - the pose leaps to a distant location, often next to an obstacle; and "if the measurement covariance is overconfident, the filter output will have discrete jumps." Nav2 users report the `map→odom` transform "jumps," corrupting the costmap.
- https://answers.ros.org/question/256634/ (AMCL jumps crazily)
- https://github.com/ros-navigation/navigation2/issues/5544 (costmap corruption from jumping map→odom)

**Signal:** deltas on `pose.pose.position` and quaternion→yaw between consecutive messages vs. `dt`; treat `odom` frame as should-be-continuous and `map` frame as allowed occasional (but bounded) correction jumps.
**Difficulty:** Medium (velocity-plausibility threshold; frame-aware).
**Why P1:** high-severity localization failure, but needs a sane per-platform velocity bound to avoid false positives.

### 11. Diagnostics regression
**Flags:** any `diagnostic_msgs/DiagnosticArray` status whose `level` rises to WARN(1) / ERROR(2) / STALE(3) - the health signals engineers publish but nobody watches live.

**Real pain:** in ROS 2 the `/diagnostics` subscription was ported with a shallow default queue, so "only the DiagnosticStatus from one of the sensors gets processed… which could overlook errors in other sensors." Diagnostics errors get silently dropped at runtime - but a log tool sees *all* of them, curing exactly that blind spot.
- https://github.com/ros/diagnostics/issues/167

**Signal:** `/diagnostics` and `/diagnostics_agg`; read `status[].level`, `status[].name`, `status[].message`; cluster and report the transitions to WARN/ERROR/STALE.
**Difficulty:** Easy (read an enum per array element).
**Why P1:** cheap and high-signal; addresses the "diagnostics people ignore" problem head-on. Promote to P0 for fleets that lean on diagnostics.

### 12. Control-loop overrun / missed deadline
**Flags:** the ros2_control real-time loop missing its configured rate - deadline overruns and missed update cycles that precede jerky, unsafe motion.

**Real pain:** the node emits *"Overrun detected! The controller manager missed its desired rate of 500 Hz. The loop took 2.139334 ms (missed cycles: 2)."*, and even the throttling of that warning is buggy ("Throttling the warnings about overruns doesn't seem to work reliably"). `ControllerUpdateStats` (missed-cycle counts) is published to `/diagnostics`.
- https://github.com/ros-controls/ros2_control/issues/2236
- https://github.com/ros-controls/ros2_control/issues/2049 (RT scheduling / jitter)
- https://control.ros.org/rolling/doc/ros2_control/controller_manager/doc/userdoc.html

**Signal:** cleanest is the `ControllerUpdateStats` missed-cycle counter on `/diagnostics` or `/controller_manager/introspection_data/*`; fallback is the rosout WARN pattern `Overrun detected`. Distinct from the existing ERROR-burst detector: this is a WARN-level pattern plus a counter, not an ERROR cluster.
**Difficulty:** Easy-Medium.
**Why P1:** exactly the "surprising thing engineers wish they could spot," and it foreshadows unsafe motion - a P0 candidate for manipulation/real-time platforms.

### 13. Node death / lifecycle wedge
**Flags:** a managed node dying (bond heartbeat lost, respawn) or a lifecycle node stuck mid-transition - a dead planner/controller is a top-severity failure.

**Real pain:**
- Nav2 lifecycle_manager logs `CRITICAL FAILURE: SERVER planner_server IS DOWN` after "it has not received a heartbeat," then tears down the whole stack. - https://github.com/ros-navigation/navigation2/issues/2752
- On a failed transition "the node is now in the deactivating (transitioning) state… future requests to activate or deactivate will be rejected" → wedged forever. - https://github.com/ros2/rclcpp/issues/1880
- An invalid transition "kills the node." - https://github.com/ros2/rclpy/issues/1209

**Signal:** `/bond` (`bond/msg/Status`) going silent past `bond_timeout`; `~/transition_event` (`lifecycle_msgs/TransitionEvent`) landing in `deactivating`/`errorprocessing` without reaching a steady goal state; a node's rosout going silent then restarting. Keys on liveliness/lifecycle topics + a small per-node state machine, not an arbitrary data topic.
**Difficulty:** Medium.
**Why P1:** severe when it happens, but requires per-node state tracking and depends on bond/lifecycle topics being recorded.

---

## P2 detectors

### 14. Out-of-order / skewed timestamps
**Flags:** two related timeline defects: (a) a topic whose `header.stamp` sequence is non-monotonic even when `log_time` is ordered (jitter, retransmit, multi-sensor merge → `TF_OLD_DATA` "ignoring data from the past"), and (b) topics whose `header.stamp` sits far from `log_time` (publishers that back-date or future-date).

**Real pain:** "rosbag records messages in the order received… network jitter/retransmit means actual Header.stamps can be out of order even though bag-level timestamps are ordered"; and "ROS and rosbag make no guarantees about… the offset between these timestamps… some publishers backdate or future-date timestamps," which is why Foxglove (which renders TF by `header.stamp` but delivers by `log_time`) added per-plot timestamp selection.
- https://answers.ros.org/question/197001/ (rosbag topics out of order)
- https://answers.ros.org/question/318536/ (understanding rosbag timestamps)
- https://github.com/ros2/rosbag2/issues/2094 (real-robot bag → TF_OLD_DATA, labeled Bug)
- https://docs.foxglove.dev/docs/visualization/playback (log_time vs header.stamp semantics)

**Signal:** per-topic count of `header.stamp[i] < header.stamp[i-1]` (fraction of inversions, max backstep); per-topic distribution of `log_time − header.stamp` (large median offset or high variance). Note the skew metric is sensitive to publisher/recorder clock offset - report the delta and label it as possible skew.
**Difficulty:** Easy-Medium.
**Why P2:** real and cheap, but often a playback/quality artifact rather than a robot-behavior bug; good as a quiet advisory.

### 15. Estimator covariance sanity
**Flags:** two related estimator footguns - (a) IMU/odom covariance sentinels: `covariance[0] == -1` ("disregard this estimate") or an all-zero block ("covariance unknown" per the `sensor_msgs` spec) being consumed as if valid; and (b) EKF/UKF covariance diagonals or state magnitudes exploding toward Inf/NaN (localization diverging).

**Real pain:** robot_localization maintainer: "The only time I have ever seen NaN values is through sensor data or ill-conditioned covariance matrices," and the filter silently adds a 1e-6 epsilon when it sees a 0 variance - a footgun. A UKF froze the whole node stuck in `clampRotation` at a rotation value of **-10636217665855.5**: "the state is exploding." All-zero IMU covariances and `-1` orientation sentinels are widely mishandled.
- https://answers.ros.org/question/272226/ (robot_localization outputs NaN from ill-conditioned covariance)
- https://github.com/cra-ros-pkg/robot_localization/issues/777 (state explosion → hang)
- https://github.com/cra-ros-pkg/robot_localization/issues/420 (gyro-only orientation, `-1` covariance)
- https://answers.ros.org/question/273372/ (exploding covariances)

**Signal:** `orientation_covariance[0]` / `angular_velocity_covariance[0]` / `linear_acceleration_covariance[0]` == `-1` or all-zero; `pose.covariance` diagonal for monotonic unbounded growth, NaN/Inf, or absurd magnitude (≥1e6).
**Difficulty:** Easy for the sentinel check; Medium for the blow-up trend.
**Why P2:** the sentinel check is a trivially cheap quick win; the divergence-trend half needs temporal windowing and is noisier, so the pair lands at P2 overall (the sentinel sub-check alone could ship early).

---

## Honorable mentions (evidence found, deprioritized for now)

- **TF_REPEATED_DATA spam** - a publisher re-emitting the same `(frame, stamp)` floods the console and "buries real errors." Easy to detect (duplicate `header.stamp` per `child_frame_id`), but it is noise-about-noise more than a robot failure. Root issue: https://github.com/ros/geometry2/issues/467
- **Disconnected TF tree / orphan frame** - "Tf has two or more unconnected trees"; run connected-components on the `/tf`+`/tf_static` edge set. Overlaps heavily with #4/#9. https://answers.ros.org/question/367864/
- **Large-message bandwidth drop** - Fast-DDS "Messages get dropped when larger than 0.5MB"; correlate per-message serialized size (in mcap) with rate/jitter. https://github.com/ros2/rmw_fastrtps/issues/739
- **Publish→receive latency growth** - `log_time − header.stamp` trending upward signals a queue backlog; partially overlaps #14 and is clock-skew sensitive. https://github.com/ros2/ros2/issues/946
- **Battery low / voltage sag / e-stop asserted** - edge-detect `sensor_msgs/BatteryState` voltage/percentage and `std_msgs/Bool` e-stop; easy, and a P1 for battery-powered field robots. https://navigation.ros.org/configuration/packages/bt-plugins/conditions/IsBatteryLow.html
- **Costmap stale / blank** - `OccupancyGrid` stamp not advancing while `/odom` shows motion, or `data[]` all-zero/degenerate. Nav2 has a cluster of duplicate reports. https://github.com/ros-navigation/navigation2/issues/3267

---

*Method caveat: GitHub's server-rendered issue pages did not reliably expose 👍/comment counts to automated fetching, and several ROS Answers pages now sit behind an anti-bot wall (question IDs remain stable). Ranking therefore reflects issue prominence, cross-repo duplication, and maintainer confirmation (e.g. navigation2#2835 reproduced on physical hardware; rclpy#630 reproduced on two DDS vendors) rather than exact vote tallies. All linked issues were confirmed to be real and on-topic.*
