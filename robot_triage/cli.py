import argparse
import sys

if __package__ in (None, ""):
    # running as a plain script: python robot_triage/cli.py file.mcap
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from robot_triage.reader import read_messages
    from robot_triage.detectors import build_detectors
    from robot_triage.report.text import render_text
else:
    from .reader import read_messages
    from .detectors import build_detectors
    from .report.text import render_text


def run(path):
    detectors = build_detectors()
    for topic, t, msg in read_messages(path):
        for det in detectors:
            det.process(topic, t, msg)

    events = []
    for det in detectors:
        events.extend(det.finish())
    events.sort(key=lambda e: e.t_start)
    return events


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="triage", description="Triage a robot log for common-sense failures."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="scan a bag and report flagged moments")
    p_run.add_argument("bag", help="path to a .mcap or .bag file")

    args = parser.parse_args(argv)
    if args.command == "run":
        print(render_text(run(args.bag), args.bag))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
