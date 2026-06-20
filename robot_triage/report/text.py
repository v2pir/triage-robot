"""Stage 3: render a list of Events as a plain-text report."""


def render_text(events, source=None):
    lines = []
    title = "triage report" + (f" for {source}" if source else "")
    lines.append(title)
    lines.append("=" * len(title))

    if not events:
        lines.append("No issues detected.")
        return "\n".join(lines)

    events = sorted(events, key=lambda e: e.t_start)
    lines.append(f"{len(events)} event(s) found:")
    lines.append("")
    for e in events:
        lines.append(f"[{e.severity.upper():>8}] {e.detector}: {e.summary}")
    return "\n".join(lines)
