"""TubeTalk AI: Streamlit entry point.

Run:
    cd frontend
    python -m streamlit run app.py

Routing is a small `page` value in session_state (home | workspace), derived from the URL on every
run. The open video and session are mirrored into the URL (?video=…&session=…) so a browser refresh
or Back restores them.
"""
import streamlit as st

import state
from components import style, theme

st.set_page_config(
    page_title="TubeTalk AI",
    page_icon=":material/smart_display:",
    layout="wide",
    initial_sidebar_state="auto",  # expanded on desktop, collapsed on phones
)
style.inject()
theme.render()  # header theme selector; right after the stylesheet so it keeps its place on every page
state.init_state()

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


flash = state.pop_flash()
if flash:
    st.toast(flash)

if st.session_state["page"] == "home":
    from views.home import show as show_home

    show_home(navigate_to_workspace=go_workspace)
else:
    from views.workspace import show as show_workspace

    show_workspace(navigate_to_home=go_home, navigate_to_workspace=go_workspace)
