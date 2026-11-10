"""TubeTalk AI brand: the logo (red rounded play button, white play triangle, "AI" badge at its
upper-right) and the wordmark ("TubeTalk" in the text colour, "AI" in red). One source for every
page, so the landing page, sidebar, dashboard and browser tab always match.

The logo is a static SVG file of our own, inlined as a data URI <img> (Streamlit's HTML sanitiser
keeps <img>, and an image needs no inline <svg> support). No user data goes into this markup.
"""
import base64
from functools import lru_cache
from pathlib import Path

LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "logo.svg"


@lru_cache
def logo_data_uri() -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")


def lockup_html(size: str = "md") -> str:
    """Logo + wordmark, e.g. for the sidebar (md) or the landing page header (lg)."""
    return (
        f'<div class="tt-brand tt-brand-{size}">'
        f'<img class="tt-logo" src="{logo_data_uri()}" alt="" aria-hidden="true">'
        '<span class="tt-wordmark">TubeTalk<span class="tt-wordmark-ai">AI</span></span>'
        "</div>"
    )
