"""Dashboard (signed in): add a YouTube video and reopen the videos in your library."""
import streamlit as st

import api_client as ac
import auth
import state
from api_client import ApiError
from components import brand, style
from components.errors import friendly_message
from components.format import fmt_date, md_escape, truncate
from components.sidebar import render_sidebar
from components.videos import load_recent_videos, open_video

GRID_COLUMNS = 3  # Streamlit stacks the columns on phones


def _first_name() -> str | None:
    user = auth.user() or {}
    name = (user.get("name") or "").strip()
    return name.split()[0] if name and name != user.get("email") else None


def show(navigate_to_workspace) -> None:
    render_sidebar(navigate_to_workspace=navigate_to_workspace, on_home=True)

    first = _first_name()
    # The name comes from the Google profile, so it goes through md_escape and plain markdown.
    st.caption(md_escape(f"Welcome back, {first}" if first else "Welcome back"))
    st.markdown(
        '<div class="tt-dash-head"><h1>Your library</h1>'
        '<div class="tt-sub">Add a YouTube video, then ask it anything. Every answer is cited to the exact '
        "moment in the transcript.</div></div>",
        unsafe_allow_html=True,  # static text only
    )

    with st.container(border=True, key="tt-add"):
        style.label("Add a video")
        with st.form("add_video", border=False):
            field, button = st.columns([5, 1.4], vertical_alignment="bottom")
            url = field.text_input(
                "YouTube link",
                placeholder="https://www.youtube.com/watch?v=…",
                label_visibility="collapsed",
            )
            submitted = button.form_submit_button("Process video", type="primary", width="stretch")
        st.caption(
            "Works with videos that have English captions. New videos take a minute or more to prepare "
            "the first time; videos you've added before open right away."
        )

    if submitted:
        if url.strip():
            _process(url.strip(), navigate_to_workspace)
        else:
            st.error(friendly_message(ApiError("INVALID_VIDEO_URL", "")))

    st.write("")
    style.label("Your videos")
    _render_recent(navigate_to_workspace)


def _process(url: str, navigate_to_workspace) -> None:
    failure = None
    with st.status("Processing video…", expanded=True) as status:
        st.write("Fetching the transcript and building the search index. This can take a minute or more for long videos.")
        try:
            resp = ac.process_video(url)
        except ApiError as exc:
            failure = exc
            status.update(label="Couldn’t process this video", state="error", expanded=False)
        else:
            status.update(label="Done", state="complete", expanded=False)
    if failure:  # shown outside the status box, which collapses
        st.error(friendly_message(failure))
        return

    video, session = resp["video"], resp["session"]
    state.invalidate_recent_videos()
    state.invalidate_sessions(video["id"])
    state.open_workspace(video, session["id"])
    state.flash("Already processed. Opened the existing video." if resp.get("reused") else "Video ready.")
    navigate_to_workspace()


def _render_recent(navigate_to_workspace) -> None:
    try:
        videos = load_recent_videos()
    except ApiError as exc:
        st.error(friendly_message(exc))
        if st.button("Try again", key="retry_recent"):
            state.invalidate_recent_videos()
            st.rerun()
        return

    if not videos:
        st.markdown(  # static markup only
            f'<div class="tt-empty"><img src="{brand.logo_data_uri()}" alt="">'
            '<div class="tt-empty-title">No videos yet</div>'
            '<div class="tt-empty-text">Paste a YouTube link above to begin.</div></div>',
            unsafe_allow_html=True,
        )
        return

    for row in range(0, len(videos), GRID_COLUMNS):
        for column, v in zip(st.columns(GRID_COLUMNS, gap="medium"), videos[row:row + GRID_COLUMNS]):
            with column:
                _render_card(v, navigate_to_workspace)


def _render_card(v: dict, navigate_to_workspace) -> None:
    with st.container(border=True, key=f"tt-card-{v['id']}"):
        if v.get("thumbnail_url"):
            st.image(v["thumbnail_url"], width="stretch")
        else:
            st.markdown(f'<div class="tt-thumb-empty"><img src="{brand.logo_data_uri()}" alt=""></div>',
                        unsafe_allow_html=True)  # static markup only
        # Untrusted text goes through md_escape and plain markdown, never into HTML-enabled calls.
        with st.container(key=f"tt-title-{v['id']}"):
            st.markdown(f"**{md_escape(truncate(v.get('title') or v['youtube_url'], 90))}**")
        bits = [b for b in (v.get("channel_name"), (v.get("transcript_language") or "").upper(), fmt_date(v.get("created_at"))) if b]
        st.caption(md_escape(" · ".join(bits)))
        if st.button("Open", key=f"open_{v['id']}", width="stretch"):
            try:
                open_video(v)
            except ApiError as exc:
                st.error(friendly_message(exc))
            else:
                navigate_to_workspace()
