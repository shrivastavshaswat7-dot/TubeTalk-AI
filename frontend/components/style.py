"""One small static stylesheet. It contains no API data, so unsafe_allow_html is safe here.

Palette: TubeTalk red (#E0002B for actions and selection, #FF0033 in the logo) with black, white and
neutral greys. Surfaces and text come from the light/dark theme in .streamlit/config.toml.
Streamlit exposes no theme class or CSS variables, so every rule here works in both themes: neutrals
are mixed from the current text colour, and red is used as a solid fill (with white text), a thin
accent or a light tint.

Selectors use Streamlit's data-testid attributes and the `st-key-…` classes of keyed containers.
Those are internal to Streamlit (pinned to 1.66.1); if one changes, the element just falls back to
Streamlit's default look.
"""
import streamlit as st

_CSS = """
<style>
:root { --tt-red: #E0002B; --tt-red-hover: #C20025; --tt-red-brand: #FF0033; --tt-red-text: #F00030; }

/* Room below Streamlit's fixed top bar (theme selector), so the first line is never tucked under it. */
[data-testid="stMainBlockContainer"].block-container { padding-top: 4.4rem; padding-bottom: 2.5rem; max-width: 1240px; }

/* ── Type ──────────────────────────────────────────────────────────────────── */
h1, h2, h3 { letter-spacing: -0.02em; font-weight: 700; }
[data-testid="stMain"] [data-testid="stMarkdownContainer"] h2 { font-size: 1.8rem; line-height: 1.2; }
[data-testid="stCaptionContainer"] { line-height: 1.45; }

/* ── Brand: logo + wordmark ("TubeTalk" in the text colour, "AI" in red) ───── */
.tt-brand { display: flex; align-items: center; gap: .55rem; margin: 0; }
.tt-brand .tt-logo { height: 30px; width: auto; display: block; }
.tt-brand-lg .tt-logo { height: 40px; }
.tt-wordmark { font-size: 1.32rem; font-weight: 800; letter-spacing: -0.03em; line-height: 1; }
.tt-brand-lg .tt-wordmark { font-size: 1.7rem; }
.tt-wordmark-ai { color: var(--tt-red-text); margin-left: .18em; }

/* Section labels in the sidebar and page */
.tt-label { text-transform: uppercase; letter-spacing: .09em; font-size: .7rem; font-weight: 700;
            opacity: .58; margin: 0 0 .45rem 0; line-height: 1.35; }

/* ── Sidebar ───────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] { border-right: 1px solid color-mix(in srgb, currentColor 9%, transparent); }
[data-testid="stSidebar"] .block-container { padding-top: 1.5rem; }
[data-testid="stSidebar"] hr { margin: 0.9rem 0; }
[data-testid="stSidebar"] .stButton > button { justify-content: flex-start; text-align: left; border-radius: 10px; }
[data-testid="stSidebar"] .stButton > button p { text-align: left; }
/* The open conversation / video: a light red tint with a red marker, not a solid block. */
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
  background: color-mix(in srgb, var(--tt-red) 13%, transparent);
  border-color: color-mix(in srgb, var(--tt-red) 38%, transparent);
  color: inherit; font-weight: 600; box-shadow: inset 3px 0 0 var(--tt-red);
}
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:hover {
  background: color-mix(in srgb, var(--tt-red) 20%, transparent); color: inherit;
}
.tt-account { display: flex; align-items: center; gap: .6rem; margin: .1rem 0 .35rem 0; min-width: 0; }
.tt-avatar { flex: 0 0 auto; width: 2rem; height: 2rem; border-radius: 50%; display: grid; place-items: center;
             background: var(--tt-red); color: #FFFFFF; font-weight: 700; font-size: .9rem; }
.tt-account-text { min-width: 0; line-height: 1.25; }
.tt-account-name { font-weight: 600; font-size: .9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tt-account-email { font-size: .78rem; opacity: .62; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

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
            border: 1px solid color-mix(in srgb, currentColor 14%, transparent);
            background: color-mix(in srgb, currentColor 4%, transparent); }
.tt-theme button { font: inherit; font-size: .78rem; line-height: 1; padding: .4rem .72rem;
                   border: 0; border-radius: 999px; background: transparent; color: inherit;
                   opacity: .72; cursor: pointer; transition: background-color .15s ease, opacity .15s ease; }
.tt-theme button:hover { opacity: 1; background: color-mix(in srgb, currentColor 8%, transparent); }
.tt-theme button[aria-checked="true"] { opacity: 1; background: var(--tt-red); color: #FFFFFF; }
.tt-theme button:focus-visible { outline: 2px solid var(--tt-red); outline-offset: 1px; }

/* ── Buttons and inputs ────────────────────────────────────────────────────── */
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--tt-red); border-color: var(--tt-red); color: #FFFFFF; font-weight: 600;
}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background: var(--tt-red-hover); border-color: var(--tt-red-hover); color: #FFFFFF;
}
[data-testid="stBaseButton-secondary"], [data-testid="stBaseLinkButton-secondary"] {
  border-color: color-mix(in srgb, currentColor 16%, transparent);
  transition: border-color .15s ease, background-color .15s ease;
}
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseLinkButton-secondary"]:hover {
  border-color: color-mix(in srgb, currentColor 40%, transparent); color: inherit;
  background: color-mix(in srgb, currentColor 6%, transparent);
}
[data-testid="stBaseButton-tertiary"]:hover { color: inherit; text-decoration: underline;
  text-decoration-color: var(--tt-red); text-underline-offset: 3px; }

/* Chat | Insights switch: the selected view is solid red. */
[data-testid="stButtonGroup"] button[data-selected="true"] {
  background: var(--tt-red) !important; border-color: var(--tt-red) !important; color: #FFFFFF !important;
}
[data-testid="stButtonGroup"] button[data-selected="true"] p { color: #FFFFFF; }

/* A neutral focus ring that stays visible in both themes, with a red edge. */
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stChatInput"]:focus-within > div {
  border-color: color-mix(in srgb, var(--tt-red) 65%, currentColor);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--tt-red) 18%, transparent);
}
[data-testid="stChatInput"] > div { border-radius: 16px; border: 1px solid color-mix(in srgb, currentColor 14%, transparent); }
[data-testid="stChatInputSubmitButton"]:not(:disabled) { background: var(--tt-red); color: #FFFFFF; border-radius: 10px; }

/* ── Video ─────────────────────────────────────────────────────────────────── */
[class*="st-key-tt-player-"] iframe {
  border-radius: 14px; display: block;
  border: 1px solid color-mix(in srgb, currentColor 10%, transparent);
}
/* Streamlit fades "stale" elements during a rerun; the player is never stale, so keep it crisp. */
[class*="st-key-tt-player-"] [data-stale="true"] { opacity: 1 !important; }

/* ── Chat: a clean conversation column ─────────────────────────────────────── */
.st-key-tt-history { padding: .35rem .3rem; }
[data-testid="stChatMessage"] { background: transparent; padding: .4rem .25rem; gap: .7rem;
                                animation: tt-rise .22s ease-out; }
/* Answers: a small red TubeTalk avatar and plain text. */
[data-testid="stChatMessageAvatarCustom"] { background: var(--tt-red); color: #FFFFFF; border-radius: 50%; }
/* Your messages: a right-aligned grey bubble, no avatar. */
[data-testid="stChatMessage"]:has([class*="st-key-tt-user-"]) { flex-direction: row-reverse; }
[data-testid="stChatMessage"]:has([class*="st-key-tt-user-"]) [data-testid="stChatMessageAvatarCustom"] { display: none; }
[data-testid="stChatMessage"]:has([class*="st-key-tt-user-"]) [data-testid="stChatMessageContent"] {
  flex: 0 1 auto; max-width: 82%; margin-left: auto; margin-right: 0;
  background: color-mix(in srgb, currentColor 8%, transparent);
  border-radius: 18px 18px 6px 18px; padding: .55rem .95rem;
}

/* Sources under an answer */
[data-testid="stChatMessage"] [data-testid="stExpander"] details {
  border-radius: 12px; border-color: color-mix(in srgb, currentColor 12%, transparent);
}
[data-testid="stChatMessage"] [data-testid="stExpander"] summary { font-size: .85rem; opacity: .85; }

/* ── Notices: one neutral surface, the meaning carried by a coloured edge and the icon ── */
[data-testid="stAlertContainer"] {
  background: color-mix(in srgb, currentColor 5%, transparent); color: inherit;
  border: 1px solid color-mix(in srgb, currentColor 11%, transparent);
  border-left: 3px solid color-mix(in srgb, currentColor 45%, transparent); border-radius: 12px;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]),
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) { border-left-color: var(--tt-red); }
[data-testid="stAlertContainer"] [data-testid="stMarkdownContainer"],
[data-testid="stAlertContainer"] [data-testid="stMarkdownContainer"] p { color: inherit; }

/* Loading */
[data-testid="stSpinner"] i { border-top-color: var(--tt-red) !important; }

/* ── Insights ──────────────────────────────────────────────────────────────── */
.st-key-tt-insights { padding-right: .35rem; }
.st-key-tt-insights h3 { font-size: 1.2rem; margin-top: .6rem; padding-bottom: .3rem;
  border-bottom: 1px solid color-mix(in srgb, currentColor 11%, transparent); }

/* ── Cards (dashboard videos, landing steps) ───────────────────────────────── */
[class*="st-key-tt-card-"], [class*="st-key-tt-step-"], .st-key-tt-add {
  border-radius: 16px !important; border-color: color-mix(in srgb, currentColor 11%, transparent) !important;
  transition: border-color .15s ease, transform .15s ease;
}
[class*="st-key-tt-card-"]:hover { border-color: color-mix(in srgb, currentColor 26%, transparent) !important; }
[class*="st-key-tt-card-"] img { border-radius: 10px; aspect-ratio: 16 / 9; object-fit: cover; }
/* Video titles: two lines at most, same height in every card of a row. */
[class*="st-key-tt-title-"] p { line-height: 1.3; margin: .15rem 0 0 0; min-height: 2.6em;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.tt-thumb-empty { aspect-ratio: 16 / 9; border-radius: 10px; display: grid; place-items: center;
                  background: color-mix(in srgb, currentColor 6%, transparent); }
.tt-thumb-empty img { width: 56px; height: auto; aspect-ratio: auto; opacity: .9; }

/* ── Dashboard (signed in) ─────────────────────────────────────────────────── */
.tt-dash-head { margin: .4rem 0 1.2rem 0; }
.tt-dash-head .tt-hello { font-size: .95rem; opacity: .7; margin: 0 0 .25rem 0; }
.tt-dash-head h1 { font-size: 2.2rem; line-height: 1.12; margin: 0 0 .35rem 0; padding: 0; }
.tt-dash-head .tt-sub { font-size: 1.02rem; line-height: 1.5; opacity: .72; margin: 0; max-width: 42rem; }
.tt-empty { text-align: center; padding: 2.4rem 1rem; border-radius: 16px;
            border: 1px dashed color-mix(in srgb, currentColor 18%, transparent); }
.tt-empty img { width: 64px; height: auto; margin: 0 auto .8rem auto; display: block; }
.tt-empty .tt-empty-title { font-weight: 700; font-size: 1.1rem; margin-bottom: .25rem; }
.tt-empty .tt-empty-text { opacity: .7; }

/* ── Landing page (signed out) ─────────────────────────────────────────────── */
.tt-nav { display: flex; align-items: center; justify-content: space-between; margin: .2rem 0 2.6rem 0; }
.tt-hero { padding-top: .4rem; }
.tt-hero .tt-eyebrow { display: inline-flex; align-items: center; gap: .45rem; font-size: .8rem; font-weight: 600;
  letter-spacing: .02em; padding: .3rem .7rem; border-radius: 999px; margin-bottom: 1.1rem;
  border: 1px solid color-mix(in srgb, currentColor 14%, transparent); }
.tt-hero .tt-eyebrow::before { content: ""; width: .5rem; height: .5rem; border-radius: 50%; background: var(--tt-red-brand); }
.tt-hero h1 { font-size: 3.3rem; line-height: 1.04; letter-spacing: -0.035em; margin: 0 0 1rem 0; padding: 0; font-weight: 800; }
.tt-hero .tt-sub { font-size: 1.14rem; line-height: 1.55; opacity: .74; margin: 0 0 1.6rem 0; max-width: 34rem; }
a.tt-google { display: inline-flex; align-items: center; gap: .65rem; padding: .78rem 1.35rem .78rem .8rem;
              border-radius: 999px; background: var(--tt-red); color: #FFFFFF !important;
              font-weight: 650; font-size: 1.02rem; text-decoration: none !important;
              box-shadow: 0 6px 18px -8px color-mix(in srgb, var(--tt-red) 70%, transparent);
              transition: background-color .15s ease, transform .15s ease; }
a.tt-google:hover { background: var(--tt-red-hover); color: #FFFFFF !important; transform: translateY(-1px); }
a.tt-google:focus-visible { outline: 2px solid var(--tt-red); outline-offset: 3px; }
a.tt-google::before { content: "G"; display: inline-grid; place-items: center; width: 1.6rem; height: 1.6rem;
                      border-radius: 50%; background: #FFFFFF; color: var(--tt-red); font-weight: 800; font-size: .95rem; }
.tt-cta-note { font-size: .85rem; opacity: .62; margin-top: .75rem; }

/* The example conversation beside the hero (static markup of a real answer). */
.tt-preview { border-radius: 20px; padding: 1.1rem; margin-top: .4rem;
              border: 1px solid color-mix(in srgb, currentColor 11%, transparent);
              background: color-mix(in srgb, currentColor 3%, transparent); }
.tt-preview-player { aspect-ratio: 16 / 7.5; border-radius: 12px; display: grid; place-items: center; margin-bottom: 1rem;
                     background: #0F0F0F; border: 1px solid color-mix(in srgb, currentColor 8%, transparent); }
.tt-preview-player img { width: 64px; height: auto; }
.tt-preview-q { margin-left: auto; width: fit-content; max-width: 85%; padding: .5rem .9rem; border-radius: 16px 16px 5px 16px;
                background: color-mix(in srgb, currentColor 8%, transparent); font-size: .93rem; margin-bottom: .75rem; }
.tt-preview-a { display: flex; gap: .6rem; font-size: .93rem; line-height: 1.5; }
.tt-preview-a .tt-dot { flex: 0 0 auto; width: 1.6rem; height: 1.6rem; border-radius: 50%; background: var(--tt-red); }
.tt-chip { display: inline-block; font-size: .78rem; font-weight: 650; padding: .12rem .5rem; border-radius: 999px; margin-left: .3rem;
           color: var(--tt-red-text); background: color-mix(in srgb, var(--tt-red) 12%, transparent); white-space: nowrap; }
.tt-preview-label { font-size: .72rem; opacity: .5; margin-top: .9rem; text-transform: uppercase; letter-spacing: .08em; }

.tt-step-no { width: 1.9rem; height: 1.9rem; border-radius: 50%; display: grid; place-items: center; font-weight: 800;
              color: var(--tt-red-text); background: color-mix(in srgb, var(--tt-red) 12%, transparent); margin-bottom: .55rem; }
.tt-step-title { font-weight: 700; margin-bottom: .2rem; }
.tt-footer { margin-top: 2.6rem; padding-top: 1.1rem; font-size: .82rem; opacity: .6;
             border-top: 1px solid color-mix(in srgb, currentColor 10%, transparent); }

@keyframes tt-rise { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) {
  [data-testid="stChatMessage"] { animation: none; }
  a.tt-google, [class*="st-key-tt-card-"] { transition: none; }
}

/* Phones: keep long video titles and the hero from dominating the screen, and leave room for the
   video above a shorter chat pane. */
@media (max-width: 640px) {
  .tt-nav { margin-bottom: 1.6rem; }
  .tt-hero h1 { font-size: 2.3rem; }
  .tt-hero .tt-sub { font-size: 1.02rem; }
  .tt-dash-head h1 { font-size: 1.7rem; }
  [data-testid="stMain"] [data-testid="stMarkdownContainer"] h2 { font-size: 1.45rem; }
  .st-key-tt-history, .st-key-tt-insights,
  [data-testid="stLayoutWrapper"]:has(> .st-key-tt-history),
  [data-testid="stLayoutWrapper"]:has(> .st-key-tt-insights) { height: 62vh !important; max-height: 62vh; }
}
</style>
"""


def inject() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def label(text: str) -> None:
    """Small uppercase section label. `text` must be a fixed string from our own code."""
    st.markdown(f'<div class="tt-label">{text}</div>', unsafe_allow_html=True)
