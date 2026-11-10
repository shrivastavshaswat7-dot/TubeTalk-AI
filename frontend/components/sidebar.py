"""Shared sidebar rendered on every page."""
import streamlit as st

import api_client as ac
import state
from api_client import ApiError
from components import style
from components.errors import friendly_message
from components.format import fmt_datetime, truncate
from components.videos import latest_session_id, load_recent_videos, open_video


def _session_label(session: dict) -> str:
    when = fmt_datetime(session.get("updated_at") or session.get("created_at")) or "Conversation"
    title = (session.get("session_title") or "").strip()
    # The backend's default title is "New Conversation" for every session, so the time is the useful label.
    return when if title in ("", "New Conversation") else f"{truncate(title, 24)} · {when}"


@st.dialog("Delete this conversation?")
def _confirm_delete(video_id: str, session_id: str, navigate_to_workspace) -> None:
    st.write("Its messages will be permanently removed. The video and its transcript are not affected.")
    left, right = st.columns(2)
    if right.button("Cancel", width="stretch"):
        st.rerun()
    if left.button("Delete", type="primary", width="stretch"):
        try:
            ac.delete_session(session_id, video_id)
        except ApiError as exc:
            st.error(friendly_message(exc))
            return
        state.clear_messages(video_id, session_id)
        state.invalidate_sessions(video_id)
        try:
            next_id = latest_session_id(video_id)  # most recent remaining, or a fresh one
        except ApiError as exc:
            st.error(friendly_message(exc))
            return
        state.switch_session(next_id)
        state.flash("Conversation deleted.")
        navigate_to_workspace()


def _render_conversations(video: dict, navigate_to_workspace) -> None:
    video_id, current = video["id"], state.get_session_id()
    style.label("Conversations")

    if st.button("New conversation", icon=":material/add:", width="stretch", key="new_convo"):
        try:
            created = ac.create_session(video_id)["session"]
        except ApiError as exc:
            st.error(friendly_message(exc))
        else:
            state.invalidate_sessions(video_id)
            state.switch_session(created["id"])
            navigate_to_workspace()

    sessions = state.get_sessions(video_id)
    if sessions is None:
        try:
            sessions = ac.list_sessions(video_id).get("sessions", [])
            state.set_sessions(video_id, sessions)
        except ApiError as exc:
            st.caption(friendly_message(exc))
            sessions = []

    for s in sessions:
        active = s["id"] == current
        if st.button(
            _session_label(s),
            key=f"sess_{s['id']}",
            type="primary" if active else "secondary",
            width="stretch",
        ) and not active:
            state.switch_session(s["id"])
            navigate_to_workspace()

    if current and st.button(
        "Delete this conversation", icon=":material/delete:", type="tertiary", key="delete_convo"
    ):
        _confirm_delete(video_id, current, navigate_to_workspace)


def _render_videos(navigate_to_workspace) -> None:
    style.label("Videos")
    try:
        videos = load_recent_videos()
    except ApiError as exc:
        st.caption(friendly_message(exc))
        return
    if not videos:
        st.caption("No videos yet.")
        return
    current = (state.get_video() or {}).get("id")
    for v in videos[:8]:
        if st.button(
            truncate(v.get("title") or v.get("youtube_url"), 40),
            key=f"rv_{v['id']}",
            help=v.get("title"),
            type="primary" if v["id"] == current else "secondary",
            width="stretch",
        ) and v["id"] != current:
            try:
                open_video(v)
            except ApiError as exc:
                st.error(friendly_message(exc))
            else:
                navigate_to_workspace()


def _render_status() -> None:
    """The health check still runs (cached), but users only see it when something is wrong."""
    with st.spinner("Connecting to the server…"):  # only visible while a sleeping backend wakes up
        healthy, _ = state.cached_health(ac.check_health)
    if healthy:
        return
    st.divider()
    # The state is also written out, so it is never conveyed by colour alone.
    left, right = st.columns([5, 1], vertical_alignment="center")
    left.caption(":red[●] Backend unreachable")
    if right.button("", icon=":material/refresh:", key="refresh_health", type="tertiary", help="Check again"):
        state.invalidate_health()
        state.invalidate_recent_videos()
        st.rerun()


def render_sidebar(navigate_to_home=None, navigate_to_workspace=None, on_home: bool = False) -> None:
    with st.sidebar:
        style.wordmark()
        st.write("")

        if not on_home and navigate_to_home:
            if st.button("All videos", icon=":material/home:", width="stretch", key="go_home"):
                state.close_workspace()
                navigate_to_home()

        video = state.get_video()
        if video and navigate_to_workspace:
            st.divider()
            _render_conversations(video, navigate_to_workspace)

        if not on_home and navigate_to_workspace:
            st.divider()
            _render_videos(navigate_to_workspace)

        _render_status()
