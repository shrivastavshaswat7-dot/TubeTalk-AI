"""Insights view: summary, key takeaways and topics (fetched once per video)."""
import streamlit as st

import api_client as ac
import state
from api_client import ApiError
from components.errors import friendly_message
from components.format import fmt_datetime, fmt_seconds, md_escape


def _text(value: str) -> str:
    """Model-written text is markdown; only `$` is escaped so prices don't turn into LaTeX."""
    return (value or "").replace("$", "\\$")


@st.dialog("Regenerate insights?")
def _confirm_regenerate(video_id: str) -> None:
    st.write("This replaces the current summary, takeaways and topics. It can take up to a minute for long videos.")
    if st.button("Regenerate", type="primary", key="confirm_regen"):
        try:
            with st.spinner("Regenerating…"):
                resp = ac.regenerate_insights(video_id)
        except ApiError as exc:
            st.error(friendly_message(exc))  # the backend keeps the previous insights; so do we
            return
        state.set_insights(video_id, resp)
        st.rerun()


def render_insights(video: dict) -> None:
    video_id = video["id"]
    data = state.get_insights(video_id)

    if data is None:
        try:
            with st.spinner("Generating insights. This can take up to a minute for long videos…"):
                data = ac.get_insights(video_id)
        except ApiError as exc:
            if exc.code == "INSIGHTS_GENERATING":
                st.info(friendly_message(exc), icon=":material/hourglass_top:")
                st.button("Check again", key="insights_check_again")
            else:
                st.error(friendly_message(exc))
                st.button("Try again", key="insights_try_again")
            return  # a click reruns the page, which fetches again
        state.set_insights(video_id, data)

    _render_body(video_id, data["insights"])


def _render_body(video_id: str, insights: dict) -> None:
    st.subheader("Summary")
    st.markdown(_text(insights.get("summary")))

    takeaways = insights.get("key_takeaways") or []
    if takeaways:
        st.subheader("Key takeaways")
        st.markdown("\n".join(f"- {_text(t)}" for t in takeaways))

    st.subheader("Topics")
    topics = insights.get("topics") or []
    if not topics:
        st.caption("No topics were identified.")
    for i, topic in enumerate(topics):
        when, name, link = st.columns([2, 5, 1], vertical_alignment="center")
        start = topic.get("start_time")
        if isinstance(start, (int, float)):
            if when.button(
                topic.get("timestamp") or fmt_seconds(start),
                key=f"topic_{i}",
                icon=":material/play_arrow:",
                help="Jump to this moment",
                width="stretch",
            ):
                state.set_player_start(start)
                st.rerun()
        else:
            when.caption("–")
        name.markdown(md_escape(topic.get("name")))
        if topic.get("timestamp_url"):
            link.link_button("", topic["timestamp_url"], icon=":material/open_in_new:", help="Open on YouTube", width="stretch")

    st.write("")
    generated = fmt_datetime(insights.get("generated_at"))
    model = insights.get("model")
    if generated or model:
        st.caption(md_escape(f"Generated {generated}" + (f" by {model}" if model else "")))
    if st.button("Regenerate insights", icon=":material/refresh:", type="tertiary", key="regen_btn"):
        _confirm_regenerate(video_id)
