"""
Page chrome for this app: the header every view opens with.

`theme.render_header` is the generic brand layer and knows nothing about this
project; this module supplies the one project-specific ingredient — the live
freshness strip.

The strip is opt-in. It describes the warehouse — last ingest, row counts,
test results — which is the right thing to see on the landing page and on How
it works, and noise above a mortgage calculator. Every other page opens with
its title and its answer.
"""
from __future__ import annotations

from freshness import get_freshness_strip
from theme import render_header


def page_header(
    title: str,
    subtitle: str = "",
    *,
    facts: bool = False,
    explain_facts: bool = False,
) -> None:
    """Byline, title, one-line subtitle — and the data-age strip where asked for."""
    strip = get_freshness_strip() if facts or explain_facts else ()
    render_header(title, subtitle, strip, explain_facts=explain_facts)
