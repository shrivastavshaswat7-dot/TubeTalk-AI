"""One small static stylesheet. It contains no API data, so unsafe_allow_html is safe here.

Palette: forest green (#176B45) for identity, primary actions and selection; red (#D94343) only for
small highlights and selected indicators. Surfaces and text come from the light/dark theme in
.streamlit/config.toml. Streamlit exposes no theme class or CSS variables, so every rule here works
in both themes: neutrals are mixed from the current text colour and the accents are used as solid
fills (with light text) or as translucent tints.

Selectors use Streamlit's data-testid attributes and the `st-key-…` classes of keyed containers.
Those are internal to Streamlit (pinned to 1.66.1); if one changes, the element just falls back to
Streamlit's default look.
"""
import streamlit as st

_CSS = """
<style>
:root { --tt-green: #176B45; --tt-green-hover: #1C7D51; --tt-red: #D94343; }

.block-container { padding-top: 2.2rem; padding-bottom: 2.5rem; max-width: 1280px; }

/* ── Type ──────────────────────────────────────────────────────────────────── */
h1, h2, h3 { letter-spacing: -0.015em; }
[data-testid="stMain"] [data-testid="stMarkdownContainer"] h2 { font-size: 1.85rem; line-height: 1.2; }
[data-testid="stCaptionContainer"] { line-height: 1.45; }

/* ── Sidebar ───────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] { border-right: 1px solid color-mix(in srgb, currentColor 10%, transparent); }
[data-testid="stSidebar"] .block-container { padding-top: 1.6rem; }
[data-testid="stSidebar"] hr { margin: 0.9rem 0; }
[data-testid="stSidebar"] .stButton > button { justify-content: flex-start; text-align: left; }
/* The active conversation / video: a green tint with a red marker, not a solid block. */
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
  background: color-mix(in srgb, var(--tt-green) 22%, transparent);
  border-color: color-mix(in srgb, var(--tt-green) 55%, transparent);
  color: inherit; font-weight: 600; box-shadow: inset 3px 0 0 var(--tt-red);
}
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:hover {
  background: color-mix(in srgb, var(--tt-green) 30%, transparent); color: inherit;
}

/* Streamlit's ⋮ menu is never shown: the header theme selector (components/theme.py) replaces it.
   It stays in the page, invisible, because the selector drives its theme items; toolbarMode =
   "viewer" (config.toml) already removes the developer items. */
[data-testid="stMainMenu"] { display: none; }
[data-testid="stMainMenuPopover"] { visibility: hidden !important; }
/* Keep Streamlit's "Running…" indicator to the left of the selector instead of underneath it. */
[data-testid="stToolbar"] { padding-right: 12rem; }

/* Header theme selector: fixed where the ⋮ menu was, so it takes no space in the page itself. */
[data-testid="stElementContainer"]:has(> [data-testid="stHtml"] .tt-theme) {
  position: fixed; top: .6rem; right: 1rem; z-index: 999991; width: auto !important;
}
.tt-theme { display: inline-flex; gap: 2px; padding: 2px; border-radius: 999px;
            border: 1px solid color-mix(in srgb, currentColor 16%, transparent);
            background: color-mix(in srgb, currentColor 4%, transparent); }
.tt-theme button { font: inherit; font-size: .78rem; line-height: 1; padding: .4rem .72rem;
                   border: 0; border-radius: 999px; background: transparent; color: inherit;
                   opacity: .72; cursor: pointer; transition: background-color .15s ease, opacity .15s ease; }
.tt-theme button:hover { opacity: 1; background: color-mix(in srgb, var(--tt-green) 12%, transparent); }
.tt-theme button[aria-checked="true"] { opacity: 1; background: var(--tt-green); color: #F2F4F0; }
.tt-theme button:focus-visible { outline: 2px solid color-mix(in srgb, var(--tt-green) 70%, currentColor);
                                 outline-offset: 1px; }

/* Wordmark */
.tt-wordmark { font-family: "Source Serif", serif; font-size: 1.35rem; font-weight: 700;
               letter-spacing: -0.01em; margin: 0; line-height: 1.2; }
.tt-tagline, .tt-label { line-height: 1.35; }
.tt-wordmark span { color: var(--tt-red); }
.tt-tagline { opacity: .65; font-size: .82rem; margin: .15rem 0 0 0; }

/* Section labels in the sidebar and page */
.tt-label { text-transform: uppercase; letter-spacing: .08em; font-size: .7rem; font-weight: 600;
            opacity: .6; margin: 0 0 .4rem 0; }

/* ── Buttons and inputs ────────────────────────────────────────────────────── */
[data-testid="stBaseButton-primary"] { background: var(--tt-green); border-color: var(--tt-green); color: #F2F4F0; }
[data-testid="stBaseButton-primary"]:hover { background: var(--tt-green-hover); border-color: var(--tt-green-hover); color: #FFFFFF; }
[data-testid="stBaseButton-secondary"], [data-testid="stBaseLinkButton-secondary"] {
  border-color: color-mix(in srgb, currentColor 18%, transparent);
  transition: border-color .15s ease, background-color .15s ease;
}
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseLinkButton-secondary"]:hover {
  border-color: var(--tt-green); color: inherit;
  background: color-mix(in srgb, var(--tt-green) 10%, transparent);
}
[data-testid="stBaseButton-tertiary"]:hover { color: inherit; text-decoration: underline;
  text-decoration-color: var(--tt-green); text-underline-offset: 3px; }

/* Chat | Insights switch: the selected view is solid green. */
[data-testid="stButtonGroup"] button[data-selected="true"] {
  background: var(--tt-green) !important; border-color: var(--tt-green) !important; color: #F2F4F0 !important;
}
[data-testid="stButtonGroup"] button[data-selected="true"] p { color: #F2F4F0; }

/* Mixed with the text colour, the ring turns lighter in dark and deeper in light, so it stays
   visible against either background. */
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stChatInput"]:focus-within > div {
  border-color: color-mix(in srgb, var(--tt-green) 70%, currentColor);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--tt-green) 28%, transparent);
}
[data-testid="stChatInput"] > div { border-radius: 12px; border: 1px solid color-mix(in srgb, currentColor 16%, transparent); }
[data-testid="stChatInputSubmitButton"]:not(:disabled) { background: var(--tt-green); color: #F2F4F0; }

/* ── Video ─────────────────────────────────────────────────────────────────── */
[class*="st-key-tt-player-"] iframe {
  border-radius: 12px; display: block;
  border: 1px solid color-mix(in srgb, currentColor 12%, transparent);
}
/* Streamlit fades "stale" elements during a rerun; the player is never stale, so keep it crisp. */
[class*="st-key-tt-player-"] [data-stale="true"] { opacity: 1 !important; }

/* ── Chat ──────────────────────────────────────────────────────────────────── */
.st-key-tt-history { padding: .35rem .2rem; }
[data-testid="stChatMessage"] { background: transparent; padding: .35rem .25rem; gap: .7rem;
                                animation: tt-rise .22s ease-out; }
[data-testid="stChatMessageAvatarCustom"] { background: var(--tt-green); color: #F2F4F0; }
/* Your messages: right-aligned tinted bubbles with a neutral avatar. */
[data-testid="stChatMessage"]:has([class*="st-key-tt-user-"]) { flex-direction: row-reverse; }
[data-testid="stChatMessage"]:has([class*="st-key-tt-user-"]) [data-testid="stChatMessageAvatarCustom"] {
  background: color-mix(in srgb, currentColor 12%, transparent); color: inherit;
}
[data-testid="stChatMessage"]:has([class*="st-key-tt-user-"]) [data-testid="stChatMessageContent"] {
  flex: 0 1 auto; max-width: 85%; margin-left: auto; margin-right: 0;
  background: color-mix(in srgb, var(--tt-green) 24%, transparent);
  border: 1px solid color-mix(in srgb, var(--tt-green) 45%, transparent);
  border-radius: 14px 14px 4px 14px; padding: .55rem .85rem;
}

/* Sources under an answer */
[data-testid="stChatMessage"] [data-testid="stExpander"] details {
  border-radius: 10px; border-color: color-mix(in srgb, currentColor 13%, transparent);
}
[data-testid="stChatMessage"] [data-testid="stExpander"] summary { font-size: .85rem; opacity: .85; }

/* ── Notices: one neutral surface, the meaning carried by a coloured edge and the icon ── */
[data-testid="stAlertContainer"] {
  background: color-mix(in srgb, currentColor 5%, transparent); color: inherit;
  border: 1px solid color-mix(in srgb, currentColor 12%, transparent);
  border-left: 3px solid var(--tt-green); border-radius: 10px;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]),
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) { border-left-color: var(--tt-red); }
[data-testid="stAlertContainer"] [data-testid="stMarkdownContainer"],
[data-testid="stAlertContainer"] [data-testid="stMarkdownContainer"] p { color: inherit; }

/* Loading */
[data-testid="stSpinner"] i { border-top-color: var(--tt-green) !important; }

/* ── Insights ──────────────────────────────────────────────────────────────── */
.st-key-tt-insights { padding-right: .35rem; }
.st-key-tt-insights h3 { font-size: 1.25rem; margin-top: .6rem; padding-bottom: .3rem;
  border-bottom: 1px solid color-mix(in srgb, currentColor 12%, transparent); }

/* Home hero */
.tt-hero h1 { font-size: 2.6rem; line-height: 1.12; letter-spacing: -0.02em; margin: 0 0 .5rem 0; padding: 0; }
.tt-hero .tt-sub { font-size: 1.05rem; line-height: 1.5; opacity: .75; margin: 0 0 1.4rem 0; max-width: 40rem; }

/* Landing page (signed out) */
.tt-landing { max-width: 46rem; margin: 2.5rem 0 1.6rem 0; }
.tt-landing .tt-wordmark { margin-bottom: 1.4rem; }
.tt-landing h1 { font-size: 2.9rem; line-height: 1.1; letter-spacing: -0.02em; margin: 0 0 .7rem 0; padding: 0; }
.tt-landing .tt-sub { font-size: 1.12rem; line-height: 1.55; opacity: .78; }
a.tt-google { display: inline-flex; align-items: center; gap: .6rem; padding: .7rem 1.25rem;
              border-radius: 999px; background: var(--tt-green); color: #F2F4F0 !important;
              font-weight: 600; text-decoration: none !important; transition: background-color .15s ease; }
a.tt-google:hover { background: var(--tt-green-hover); color: #FFFFFF !important; }
a.tt-google:focus-visible { outline: 2px solid color-mix(in srgb, var(--tt-green) 70%, currentColor); outline-offset: 2px; }
a.tt-google::before { content: "G"; display: inline-grid; place-items: center; width: 1.35rem; height: 1.35rem;
                      border-radius: 50%; background: #FFFFFF; color: #176B45; font-weight: 700; font-size: .85rem; }

@keyframes tt-rise { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { [data-testid="stChatMessage"] { animation: none; } }

/* Phones: keep long video titles and the hero from dominating the screen, and leave room for the
   video above a shorter chat pane. */
@media (max-width: 640px) {
  .tt-hero h1 { font-size: 1.9rem; }
  .tt-landing { margin-top: 1.2rem; }
  .tt-landing h1 { font-size: 2.1rem; }
  [data-testid="stMain"] [data-testid="stMarkdownContainer"] h2 { font-size: 1.45rem; }
  .st-key-tt-history, .st-key-tt-insights,
  [data-testid="stLayoutWrapper"]:has(> .st-key-tt-history),
  [data-testid="stLayoutWrapper"]:has(> .st-key-tt-insights) { height: 62vh !important; max-height: 62vh; }
}
</style>
"""


def inject() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def wordmark() -> None:
    st.markdown('<div class="tt-wordmark">Tube<span>Talk</span> AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="tt-tagline">Don’t just watch. Understand and interact.</div>', unsafe_allow_html=True)


def label(text: str) -> None:
    """Small uppercase section label. `text` must be a fixed string from our own code."""
    st.markdown(f'<div class="tt-label">{text}</div>', unsafe_allow_html=True)
