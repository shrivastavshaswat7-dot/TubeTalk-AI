"""Video workspace: header, the player on the left and Chat | Insights on the right."""
import streamlit as st

import api_client as ac
import state
from api_client import ApiError
from components.chat import HISTORY_HEIGHT, render_chat
from components.errors import friendly_message
from components.format import fmt_date, md_escape
from components.insights import render_insights
from components.sidebar import render_sidebar

VIEWS = ["Chat", "Insights"]
PANE_HEIGHT = HISTORY_HEIGHT + 64  # chat history plus its input, so both views are the same height
# Errors that mean "this ?video=…&session=… link doesn't point at anything usable".
_LINK_ERRORS = {"VALIDATION_ERROR", "VIDEO_NOT_FOUND", "SESSION_NOT_FOUND", "SESSION_VIDEO_MISMATCH"}


def show(navigate_to_home, navigate_to_workspace) -> None:
    _restore_from_query_params()
    video, session_id = state.get_video(), state.get_session_id()

    render_sidebar(navigate_to_home=navigate_to_home, navigate_to_workspace=navigate_to_workspace)

    if not video or not session_id:
        st.warning("No video is open.", icon=":material/info:")
        if st.button("Back to all videos", key="back_home"):
            state.close_workspace()
            navigate_to_home()
        return

    _render_header(video)

    # Video first: it stays on the left on desktop, stacks above the chat on narrow screens, and is
    # rendered before a slow request in the right pane. Keeping it at the same position in the
    # element tree is what lets the iframe (and playback) survive reruns. Only an explicit seek
    # changes the key, which remounts the player at the requested time (even the same time again).
    player, pane = st.columns([11, 9], gap="large")
    with player, st.container(key=f"tt-player-{state.get_player_seek()}"):
        _render_player(video)
    with pane:
        # st.tabs would run every tab body on each rerun (and so generate insights on every chat
        # message); a switch lets only the active view execute.
        view = st.segmented_control("View", VIEWS, default="Chat", key="workspace_view", label_visibility="collapsed") or "Chat"
        if view == "Chat":
            render_chat(video, session_id)
        else:
            # Scrolls on its own like the chat history, so the player stays in view.
            with st.container(height=PANE_HEIGHT, border=False, key="tt-insights"):
                render_insights(video)


def _restore_from_query_params() -> None:
    """Make the open video and session match ?video=…&session=…. After a refresh session_state may be
    empty, and after browser Back the URL may name a different video or conversation than the one
    still open. Nothing is fetched when they already match."""
    video_id, session_id = state.read_query_params()
    if not video_id or not session_id:
        return
    current = state.get_video()
    if current and current.get("id") == video_id and state.get_session_id() == session_id:
        return
    try:
        video = ac.get_video(video_id)["video"]
        messages = ac.get_messages(session_id, video_id)["messages"]  # also validates ownership
    except ApiError as exc:
        if exc.code in _LINK_ERRORS:
            st.error("That conversation couldn’t be reopened. It may have been deleted or the link is wrong.")
        else:
            st.error(friendly_message(exc))
        state.close_workspace()
        return
    if video.get("processing_status") != "completed":
        st.error(friendly_message(ApiError("VIDEO_NOT_READY", "")))
        state.close_workspace()
        return
    state.open_workspace(video, session_id)
    state.set_messages(video_id, session_id, messages)


def _render_header(video: dict) -> None:
    title_col, link_col = st.columns([5, 1.3], vertical_alignment="center")
    with title_col:
        st.markdown(f"## {md_escape(video.get('title') or 'Untitled video')}")
    with link_col:
        if video.get("youtube_url"):
            st.link_button("Open on YouTube", video["youtube_url"], icon=":material/open_in_new:", width="stretch")

    bits = [
        video.get("channel_name"),
        f"{(video.get('transcript_language') or '').upper()} transcript" if video.get("transcript_language") else None,
        f"Added {fmt_date(video.get('created_at'))}" if video.get("created_at") else None,
        "Transcript ready" if video.get("processing_status") == "completed" else (video.get("processing_status") or "").replace("_", " "),
    ]
    st.caption(md_escape(" · ".join(b for b in bits if b)))


def _render_player(video: dict) -> None:
    url = video.get("youtube_url")
    if not url:
        st.caption("No video available.")
        return
    # Autoplay only once the user has clicked a timestamp, and it then stays on: flipping it back off
    # would change the iframe src and reload (and stop) the player on the next unrelated rerun.
    # Browsers may still block autoplay; the player then just waits, paused, at the right time.
    st.video(url, start_time=state.get_player_start(), autoplay=state.get_player_seek() > 0)
    st.caption("Select a timestamp in an answer or topic to jump to that moment.")
