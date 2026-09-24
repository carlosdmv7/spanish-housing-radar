"""
Page chrome for this app: the header every view opens with.

`theme.render_header` is the generic brand layer and knows nothing about this
project; this module supplies the one project-specific ingredient — the live
freshness strip — so a view needs a single call and cannot ship a header
without its data-age line.
"""
from __future__ import annotations

from freshness import get_freshness_strip
from theme import render_header


def page_header(title: str, subtitle: str = "", *, explain_facts: bool = False) -> None:
    """Byline, title, one-line subtitle, freshness strip — in that order."""
    render_header(title, subtitle, get_freshness_strip(), explain_facts=explain_facts)
