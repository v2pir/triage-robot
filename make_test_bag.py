# make_test_bag.py
#
# Synthetic .mcap that plants one failure for each detector:
#   * dropout     : /camera silent from t=20s to t=25s
#   * range       : /battery_state percentage spikes to 1.4 (>100%) at t=10s
#   * jump        : /odom position teleports +5m at t=30s
#   * divergence  : /cmd_vel says 0.5 m/s but /odom reads ~0 (stuck) t=40-43s
#   * error_burst : /rosout emits a run of ERROR logs t=41-42s
#   * freeze      : /imu value stuck at one reading t=50-53s
import json
import time

from mcap.writer import Writer


def js(d):
    return json.dumps(d).encode()


with open("test.mcap", "wb") as f:
    w = Writer(f)
    w.start()
    schema = w.register_schema(
        name="Json", encoding="jsonschema", data=js({"type": "object"})
    )

    def channel(topic):
        return w.register_channel(topic=topic, message_encoding="json", schema_id=schema)

    cam = channel("/camera")
    imu = channel("/imu")
    cmd = channel("/cmd_vel")
    odom = channel("/odom")
    rosout = channel("/rosout")
    battery = channel("/battery_state")

    t0 = time.time_ns()
    px = 0.0  # integrated odom x position
    for i in range(600):  # 60 seconds at 10 Hz
        t = t0 + i * 100_000_000
        secs = i / 10.0

        # /camera: silent from 20s to 25s  -> dropout
        if not (200 <= i < 250):
            w.add_message(cam, log_time=t, publish_time=t, data=js({"frame": i}))

        # /imu: normally changes; frozen at one value 50s-53s  -> freeze
        imu_val = 500 if (50.0 <= secs < 53.0) else i
        w.add_message(imu, log_time=t, publish_time=t, data=js({"i": imu_val}))

        # /cmd_vel: always commanding forward 0.5 m/s, gentle turn.
        cmd_x, cmd_z = 0.5, 0.2
        w.add_message(
            cmd, log_time=t, publish_time=t,
            data=js({"linear": {"x": cmd_x, "y": 0, "z": 0},
                     "angular": {"x": 0, "y": 0, "z": cmd_z}}),
        )

        # /odom: follows the command, except 40s-43s the robot is stuck
        # (actual velocity ~0 despite the command)  -> divergence
        stuck = 40.0 <= secs < 43.0
        act_x = 0.02 if stuck else cmd_x
        act_z = 0.0 if stuck else cmd_z

        px += act_x * 0.1                # integrate position
        if abs(secs - 30.0) < 0.05:      # one unphysical teleport  -> jump
            px += 5.0

        w.add_message(
            odom, log_time=t, publish_time=t,
            data=js({"pose": {"pose": {"position": {"x": px, "y": 0, "z": 0}}},
                     "twist": {"twist": {"linear": {"x": act_x, "y": 0, "z": 0},
                                         "angular": {"x": 0, "y": 0, "z": act_z}}}}),
        )

        # /rosout: quiet, except a burst of ERRORs while stuck  -> error_burst
        if 41.0 <= secs < 42.0:
            w.add_message(
                rosout, log_time=t, publish_time=t,
                data=js({"level": 40, "name": "motor_driver",
                         "msg": "left wheel current limit exceeded"}),
            )

        # /battery_state: healthy, but a glitchy 140% reading 10s-11s  -> range
        pct = 1.4 if (10.0 <= secs < 11.0) else max(0.0, 0.85 - secs * 0.002)
        w.add_message(
            battery, log_time=t, publish_time=t, data=js({"percentage": pct})
        )

    w.finish()

print("wrote test.mcap")
