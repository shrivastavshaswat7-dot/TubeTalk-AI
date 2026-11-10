"""Home: submit a YouTube link and reopen earlier videos."""
import streamlit as st

import api_client as ac
import state
from api_client import ApiError
from components import style
from components.errors import friendly_message
from components.format import fmt_date, md_escape, truncate
from components.sidebar import render_sidebar
from components.videos import load_recent_videos, open_video


def show(navigate_to_workspace) -> None:
    render_sidebar(navigate_to_workspace=navigate_to_workspace, on_home=True)

    st.markdown(
        '<div class="tt-hero"><h1>Talk to any YouTube video.</h1>'
        '<div class="tt-sub">Paste a link, ask questions, and get answers cited to the exact moment in the transcript.</div></div>',
        unsafe_allow_html=True,  # static text only
    )

    with st.form("add_video", border=False):
        field, button = st.columns([5, 1.3], vertical_alignment="bottom")
        url = field.text_input(
            "YouTube link",
            placeholder="https://www.youtube.com/watch?v=…",
            label_visibility="collapsed",
        )
        submitted = button.form_submit_button("Process video", type="primary", width="stretch")
    st.caption(
        "Works with videos that have English captions. Long videos can take a minute or more to process. "
        "YouTube sometimes blocks transcript requests from cloud servers; if a new video can't be processed, "
        "try one of your videos below."
    )

    if submitted:
        if url.strip():
            _process(url.strip(), navigate_to_workspace)
        else:
            st.error(friendly_message(ApiError("INVALID_VIDEO_URL", "")))

    st.write("")
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
        st.info("No videos yet. Paste a YouTube link above to begin.", icon=":material/video_library:")
        return

    for v in videos:
        thumb, info, action = st.columns([1.4, 6, 1.4], vertical_alignment="center")
        with thumb:
            if v.get("thumbnail_url"):
                st.image(v["thumbnail_url"], width="stretch")
        with info:
            # Untrusted text goes through md_escape and plain markdown, never into HTML-enabled calls.
            st.markdown(f"**{md_escape(truncate(v.get('title') or v['youtube_url'], 90))}**")
            bits = [b for b in (v.get("channel_name"), (v.get("transcript_language") or "").upper(), fmt_date(v.get("created_at"))) if b]
            st.caption(md_escape(" · ".join(bits)))
        with action:
            if st.button("Open", key=f"open_{v['id']}", width="stretch"):
                try:
                    open_video(v)
                except ApiError as exc:
                    st.error(friendly_message(exc))
                else:
                    navigate_to_workspace()
