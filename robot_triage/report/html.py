"""Stage 4: a pretty, one-click HTML report.

Each flagged moment gets two ways to replay it:

  * "Open in Foxglove" -- a deep link (``?ds=remote-file&ds.url=...&time=...``)
    that seeks Foxglove's playhead to the exact instant. Requires the bag to be
    reachable at an HTTP URL, so it only appears when you pass ``--bag-url``.
  * "Clip" -- a local ``.mcap`` cut around the moment that you drag into any
    viewer. Always works offline; appears when you pass ``--clips``.
"""

import html
import os
from datetime import datetime, timezone
from pathlib import Path

from ..reader import bag_start_ns

SEV_COLOR = {"info": "#3b82f6", "warn": "#f59e0b", "critical": "#ef4444"}


def _rfc3339(ns):
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"


def _foxglove_link(bag_url, seek_ns):
    from urllib.parse import quote

    return (
        "https://app.foxglove.dev/~/view"
        f"?ds=remote-file&ds.url={quote(bag_url, safe='')}"
        f"&time={quote(_rfc3339(seek_ns), safe='')}"
    )


def render_html(events, bag_path, bag_url=None, clips=None):
    """Return an HTML report string. ``clips`` is a per-event list of file paths."""
    t0 = bag_start_ns(bag_path)
    name = html.escape(os.path.basename(str(bag_path)))

    rows = []
    for i, e in enumerate(events):
        seek_ns = t0 + int(e.t_start * 1e9)
        color = SEV_COLOR.get(e.severity, "#6b7280")

        actions = []
        if bag_url:
            actions.append(
                f'<a href="{html.escape(_foxglove_link(bag_url, seek_ns))}" '
                f'target="_blank">&#9654; Open in Foxglove</a>'
            )
        if clips and i < len(clips) and clips[i]:
            clip_abs = Path(clips[i]).resolve()
            actions.append(
                f'<a href="file://{html.escape(str(clip_abs))}">&#8615; Clip</a>'
            )
        actions.append(f'<span class="seek">seek {_rfc3339(seek_ns)}</span>')

        rows.append(
            f"""
        <tr>
          <td><span class="sev" style="background:{color}">{html.escape(e.severity)}</span></td>
          <td class="det">{html.escape(e.detector)}</td>
          <td class="t">{e.t_start:.1f}s</td>
          <td class="sum">{html.escape(e.summary)}</td>
          <td class="act">{' &nbsp; '.join(actions)}</td>
        </tr>"""
        )

    body = (
        "".join(rows)
        if rows
        else '<tr><td colspan="5" class="none">No issues detected.</td></tr>'
    )
    hint = "" if bag_url else (
        '<p class="hint">Tip: pass <code>--bag-url &lt;https URL to this bag&gt;</code> '
        "to enable one-click <b>Open in Foxglove</b> links.</p>"
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>triage - {name}</title>
<style>
  body {{ font: 14px/1.5 -apple-system, system-ui, sans-serif; margin: 2rem; color: #111; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 .25rem; }}
  .meta {{ color: #666; margin-bottom: 1.5rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: .5rem .6rem; border-bottom: 1px solid #eee; vertical-align: top; }}
  th {{ font-size: .75rem; text-transform: uppercase; letter-spacing: .04em; color: #888; }}
  .sev {{ color: #fff; padding: .1rem .5rem; border-radius: 999px; font-size: .72rem; text-transform: uppercase; }}
  .det {{ font-family: ui-monospace, monospace; color: #444; }}
  .t {{ font-variant-numeric: tabular-nums; color: #444; white-space: nowrap; }}
  .act a {{ margin-right: .3rem; text-decoration: none; color: #2563eb; white-space: nowrap; }}
  .seek {{ color: #999; font-size: .78rem; }}
  .none {{ color: #16a34a; text-align: center; padding: 2rem; }}
  .hint {{ color: #666; background: #f8f8f8; padding: .6rem .8rem; border-radius: 6px; }}
  code {{ background: #eee; padding: 0 .3rem; border-radius: 3px; }}
</style></head><body>
  <h1>Robot log triage</h1>
  <div class="meta">{name} - {len(events)} flagged moment(s)</div>
  {hint}
  <table>
    <tr><th>severity</th><th>detector</th><th>time</th><th>what happened</th><th>replay</th></tr>
    {body}
  </table>
</body></html>"""
