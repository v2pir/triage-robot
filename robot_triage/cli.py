import argparse
import os.path
import sys

if __package__ in (None, ""):
    # Running as a plain script: `python triage/cli.py file.mcap`.
    # Put the project root on sys.path so `triage` is importable as a package.
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from robot_triage.reader import read_messages
    from robot_triage.detectors import build_detectors
    from robot_triage.config import load_config
    from robot_triage.report.text import render_text
    from robot_triage.report.html import render_html
    from robot_triage.replay import extract_clips
else:
    from .reader import read_messages
    from .detectors import build_detectors
    from .config import load_config
    from .report.text import render_text
    from .report.html import render_html
    from .replay import extract_clips


def run(path, config=None):
    """Read a bag, run every enabled detector, and return the list of Events."""
    detectors = build_detectors(config)
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
    p_run.add_argument("--html", metavar="FILE", help="also write an HTML report")
    p_run.add_argument(
        "--clips",
        nargs="?",
        const="clips",
        metavar="DIR",
        help="extract a short .mcap clip per event into DIR (default: ./clips)",
    )
    p_run.add_argument(
        "--bag-url",
        metavar="URL",
        help="public https URL of this bag; enables one-click Foxglove links in --html",
    )
    p_run.add_argument(
        "--config",
        metavar="FILE",
        help="YAML/JSON config: remap topics, tune thresholds, enable/disable detectors",
    )

    args = parser.parse_args(argv)

    if args.command == "run":
        if not os.path.exists(args.bag):
            print(f"triage: no such file: {args.bag}", file=sys.stderr)
            return 2
        config = load_config(args.config)
        try:
            events = run(args.bag, config)
        except Exception as exc:
            print(f"triage: could not read {args.bag}: {exc}", file=sys.stderr)
            return 1
        print(render_text(events, args.bag))

        clips = None
        if args.clips:
            clips = extract_clips(args.bag, events, args.clips)
            print(f"\nWrote {len(clips)} clip(s) to {args.clips}/")

        if args.html:
            with open(args.html, "w") as f:
                f.write(render_html(events, args.bag, bag_url=args.bag_url, clips=clips))
            print(f"Wrote HTML report to {args.html}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
