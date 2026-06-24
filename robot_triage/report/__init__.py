"""Stage 3/4: turn Events into something a human reads."""

from .text import render_text
from .html import render_html

__all__ = ["render_text", "render_html"]
