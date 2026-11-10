"""Public landing page: what TubeTalk AI does, and Google sign-in. Calls no backend API."""
import html

import streamlit as st

import auth
from components import brand, style

_STEPS = (
    ("Paste a YouTube link", "TubeTalk reads the video's English captions and prepares them for questions."),
    ("Ask in plain language", "Answers come only from the transcript. If the video doesn't cover it, you're told."),
    ("Jump to the moment", "Every answer cites its timestamps; select one and the player starts right there."),
)

# An answer TubeTalk gave for a real video ("Give me 2 Minutes… Fear of Speaking English"), shown as
# static markup so visitors see the product before signing in.
_PREVIEW = (
    '<div class="tt-preview" aria-label="Example conversation">'
    '<div class="tt-preview-player"><img src="{logo}" alt=""></div>'
    '<div class="tt-preview-q">How long should each practice session be?</div>'
    '<div class="tt-preview-a"><span class="tt-dot" aria-hidden="true"></span>'
    "<div>Each practice session should be no longer than about half an hour."
    '<span class="tt-chip">00:39–01:31</span></div></div>'
    '<div class="tt-preview-label">Example answer from a real video</div>'
    "</div>"
)


@st.fragment(run_every=auth.LINK_CHECK_SECONDS)
def _sign_in_link() -> None:
    """Redrawn every LINK_CHECK_SECONDS so a tab left open never offers a used or stale link (its
    one-time state may have been used by a sign-in in another tab)."""
    url = html.escape(auth.login_url(), quote=True)
    # A new tab: on Streamlit Community Cloud the app runs in a sandboxed frame that may not
    # navigate the whole page, and Google's sign-in page refuses to load inside a frame. The new
    # tab comes back signed in (the PKCE verifier is kept on the server, not in this session).
    st.markdown(
        f'<a class="tt-google" href="{url}" target="_blank" rel="noopener">Continue with Google</a>'
        '<div class="tt-cta-note">Sign-in opens in a new tab. Your videos and conversations stay '
        "private to your account.</div>",
        unsafe_allow_html=True,
    )


def show(error: str | None = None) -> None:
    # Static markup; the only dynamic values are our own logo and sign-in address (escaped).
    st.markdown(f'<div class="tt-nav">{brand.lockup_html("lg")}</div>', unsafe_allow_html=True)

    hero, preview = st.columns([1.1, 1], gap="large", vertical_alignment="center")
    with hero:
        st.markdown(
            '<div class="tt-hero"><div class="tt-eyebrow">AI answers from video transcripts</div>'
            "<h1>Talk to any YouTube video.</h1>"
            '<div class="tt-sub">Paste a link, ask questions, and get answers cited to the exact moment in '
            "the transcript.</div></div>",
            unsafe_allow_html=True,
        )
        if error:
            st.error(error, icon=":material/error:")
        _sign_in_link()
    with preview:
        st.markdown(_PREVIEW.format(logo=brand.logo_data_uri()), unsafe_allow_html=True)

    st.write("")
    st.write("")
    style.label("How it works")
    for i, (column, (title, text)) in enumerate(zip(st.columns(len(_STEPS)), _STEPS), start=1):
        with column, st.container(border=True, key=f"tt-step-{i}"):
            st.markdown(f'<div class="tt-step-no">{i}</div><div class="tt-step-title">{title}</div>',
                        unsafe_allow_html=True)
            st.caption(text)

    st.markdown(
        '<div class="tt-footer">Your videos, conversations and insights are visible only to you. English '
        "captions only; long videos take a minute or more to prepare the first time.</div>",
        unsafe_allow_html=True,
    )
