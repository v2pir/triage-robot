"""Small helpers shared across detectors."""


def field(msg, path, default=None):
    """Read a nested field from a decoded message by dotted ``path``.

    Works on both JSON-decoded dicts (``msg["twist"]["angular"]["z"]``) and
    deserialized ROS message objects (``msg.twist.angular.z``), so detectors
    don't care which format the bag was in.

        field(odom, "twist.twist.angular.z")
    """
    cur = msg
    for part in path.split("."):
        if cur is None:
            return default
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
    return default if cur is None else cur
