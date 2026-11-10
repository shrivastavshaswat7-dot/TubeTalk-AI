"""Public landing page: what TubeTalk AI does, and Google sign-in. Calls no backend API."""
import html

import streamlit as st

import auth
from components import style

_FEATURES = (
    ("Paste a YouTube link", "TubeTalk reads the video's English captions and prepares them for questions."),
    ("Ask in plain language", "Answers come only from the transcript. If the video doesn't cover it, you're told."),
    ("Jump to the moment", "Every answer cites its timestamps; select one and the player starts right there."),
)


def show(error: str | None = None) -> None:
    # Static markup; the only dynamic value is our own sign-in address, escaped for the attribute.
    st.markdown(
        '<div class="tt-landing">'
        '<div class="tt-wordmark">Tube<span>Talk</span> AI</div>'
        "<h1>Talk to any YouTube video.</h1>"
        '<div class="tt-sub">Paste a link, ask questions, and get answers cited to the exact moment in '
        "the transcript.</div></div>",
        unsafe_allow_html=True,
    )
    if error:
        st.error(error, icon=":material/error:")

    url = html.escape(auth.login_url(), quote=True)
    # A new tab: on Streamlit Community Cloud the app runs in a sandboxed frame that may not navigate
    # the whole page, and Google's sign-in page refuses to load inside a frame. The new tab comes back
    # signed in (the PKCE verifier is kept on the server, not in this browser session).
    st.markdown(
        f'<a class="tt-google" href="{url}" target="_blank" rel="noopener">Continue with Google</a>',
        unsafe_allow_html=True,
    )
    st.caption("Sign-in opens in a new tab. Sign in to get your own private library of videos and conversations.")

    st.write("")
    style.label("How it works")
    for column, (title, text) in zip(st.columns(len(_FEATURES)), _FEATURES):
        with column, st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(text)

    st.write("")
    st.caption(
        "Your videos, conversations and insights are visible only to you. English captions only; long "
        "videos take a minute or more to prepare the first time."
    )
