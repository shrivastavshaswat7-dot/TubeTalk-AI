"""TubeTalk AI: Streamlit entry point.

Run:
    cd frontend
    python -m streamlit run app.py

Signed out, every address shows the public landing page (Google sign-in). Signed in, routing is a
small `page` value in session_state (home | workspace), derived from the URL on every run. The open
video and session are mirrored into the URL (?video=…&session=…) so a browser refresh or Back
restores them (after signing in again: a reload starts a new browser session).
"""
import streamlit as st

import auth
import state
from components import style, theme
from config import MISSING_API_URL_MESSAGE, MISSING_AUTH_MESSAGE, get_api_base_url, missing_auth_settings

st.set_page_config(
    page_title="TubeTalk AI",
    page_icon=":material/smart_display:",
    layout="wide",
    initial_sidebar_state="auto",  # expanded on desktop, collapsed on phones
)
style.inject()
theme.render()  # header theme selector; right after the stylesheet so it keeps its place on every page

if not get_api_base_url():  # a deployment without the backend address: say so, call nothing
    st.error(MISSING_API_URL_MESSAGE, icon=":material/settings:")
    st.stop()
missing = missing_auth_settings()
if missing:
    st.error(MISSING_AUTH_MESSAGE.format(names=", ".join(missing)), icon=":material/settings:")
    st.stop()

sign_in_error = auth.handle_callback()  # the return from Google, if this is it (clears the URL)
signed_in = auth.current_session() is not None  # may refresh the token, or end an expired session
state.init_state()

flash = state.pop_flash()  # after the session check, so "Your session has expired" shows right away
if flash:
    st.toast(flash)

if not signed_in:
    from views.landing import show as show_landing

    show_landing(error=sign_in_error)
    st.stop()

# The URL decides the page on every run, not just the first: Streamlit can reattach a reloaded tab
# to its existing session, so a remembered page could otherwise outlive the URL it came from.
# Every navigation writes the URL first (open_workspace / switch_session / close_workspace).
video_id, session_id = state.read_query_params()
st.session_state["page"] = "workspace" if video_id and session_id else "home"


def go_home() -> None:
    st.session_state["page"] = "home"
    st.rerun()


def go_workspace() -> None:
    st.session_state["page"] = "workspace"
    st.rerun()


if st.session_state["page"] == "home":
    from views.home import show as show_home

    show_home(navigate_to_workspace=go_workspace)
else:
    from views.workspace import show as show_workspace

    show_workspace(navigate_to_home=go_home, navigate_to_workspace=go_workspace)
