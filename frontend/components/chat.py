"""Chat view for the video workspace."""
import streamlit as st

import api_client as ac
import state
from api_client import ApiError
from components.errors import friendly_message
from components.format import fmt_range, fmt_seconds, md_escape, truncate

HISTORY_HEIGHT = 520
EXCERPT_CHARS = 260
MAX_TOPIC_STARTERS = 3
SUMMARY_PROMPT = "Summarise this video"
AVATARS = {"user": ":material/person:", "assistant": ":material/subtitles:"}
QUEUED_PROMPT = "queued_prompt"  # a prompt waiting to be sent on the next run (starter / retry)
VIEW_KEY = "workspace_view"  # the workspace's Chat | Insights switch
# Only used to pick the spinner text; the backend decides the actual routing.
_OVERVIEW_HINTS = ("summar", "overview", "about", "main point", "key point", "takeaway", "tl;dr", "gist", "topics")


def _answer_text(text: str) -> str:
    """Answers are markdown; only `$` is escaped so prices don't turn into LaTeX."""
    return (text or "").replace("$", "\\$")


def open_summary() -> None:
    """Button callback: switch the workspace to the Insights view (runs before the next render)."""
    st.session_state[VIEW_KEY] = "Insights"


# ── Rendering ─────────────────────────────────────────────────────────────────


def _render_sources(sources: list[dict], key: str) -> None:
    """Sources sorted by video time. No nested expanders (Streamlit forbids them) and keys include
    the message, because the same chunk can be cited by several answers.

    kind: "summary" = answered from the video summary; "topic" = transcript at an Insights topic's
    timestamp; "transcript" (or missing, for older messages) = retrieved by similarity."""
    from_summary = any(s.get("kind") == "summary" for s in sources)
    timed = sorted((s for s in sources if s.get("kind") != "summary"), key=lambda s: s.get("start_time") or 0)

    if from_summary:
        note, action = st.columns([3, 1.4], vertical_alignment="center")
        note.caption("Answered from the video summary, which is generated from the full transcript.")
        action.button("View summary", key=f"summary_{key}", icon=":material/article:", type="tertiary",
                      on_click=open_summary)
    if not timed:
        return

    with st.expander(f"{'Topics' if from_summary else 'Sources'} ({len(timed)})"):
        for i, src in enumerate(timed):
            seek, link = st.columns([4, 1], vertical_alignment="center")
            start = src.get("start_time")
            is_topic = src.get("kind") == "topic"
            label = fmt_seconds(start) if is_topic else fmt_range(start, src.get("end_time"))
            if isinstance(start, (int, float)):
                if seek.button(label, key=f"seek_{key}_{i}", icon=":material/play_arrow:",
                               help="Jump to this moment in the player", width="stretch"):
                    state.set_player_start(start)
                    st.rerun()
            else:
                seek.caption(label)
            if src.get("timestamp_url"):
                link.link_button("", src["timestamp_url"], icon=":material/open_in_new:", help="Open on YouTube", width="stretch")
            if is_topic and src.get("topic"):
                st.markdown(f"**{md_escape(src['topic'])}**")
            st.caption(md_escape(truncate(src.get("content"), EXCERPT_CHARS)))


def _user_text(content: str, key: str) -> None:
    """The keyed container only gives the stylesheet a class to tell your messages from answers."""
    with st.container(key=f"tt-user-{key}"):
        st.markdown(md_escape(content))


def _render_message(msg: dict, key: str) -> None:
    role = msg.get("role", "user")
    content = msg.get("content", "")
    with st.chat_message(role, avatar=AVATARS.get(role)):
        if role == "user":
            _user_text(content, key)
            return
        sources = msg.get("sources") or []
        if any(s.get("kind") == "clarification" for s in sources):  # asked what the user meant
            st.markdown(md_escape(content))
            st.caption("Reply with a bit more detail and I’ll look it up in the video.")
            return
        if sources:  # a grounded answer always carries its sources
            st.markdown(_answer_text(content))
            standalone = msg.get("standalone_question")
            from_summary = any(s.get("kind") == "summary" for s in sources)
            if standalone and not from_summary and standalone.strip() != msg.get("_asked", "").strip():
                st.caption(f"Searched as: {md_escape(standalone)}")
            _render_sources(sources, key)
        else:  # the transcript did not contain the answer
            st.info(content, icon=":material/search_off:")


def _topic_questions(video_id: str) -> list[str]:
    """Topic questions the backend has already checked against this video's transcript (same
    retrieval and threshold as a real question). Never triggers insight generation. Only a result
    from ready insights is cached, so suggestions appear once insights exist."""
    cached = state.get_suggestions(video_id)
    if cached is not None:
        return cached
    try:
        resp = ac.get_suggestions(video_id)
    except ApiError:
        return []
    questions = (resp.get("suggestions") or [])[:MAX_TOPIC_STARTERS]
    if resp.get("insights_ready"):
        state.set_suggestions(video_id, questions)
    return questions


def _render_empty(video_id: str) -> None:
    st.markdown("**Ask anything about this video.**")
    st.caption("Answers come only from its transcript. If something isn’t covered, you’ll be told.")
    left, right = st.columns(2)
    if left.button(SUMMARY_PROMPT, key="starter_summary", icon=":material/summarize:", width="stretch"):
        st.session_state[QUEUED_PROMPT] = SUMMARY_PROMPT
        st.rerun()
    right.button("View summary", key="starter_view_summary", icon=":material/article:", width="stretch",
                 on_click=open_summary)
    questions = _topic_questions(video_id)
    if questions:
        st.caption("Or ask about a topic from the video:")
        for i, q in enumerate(questions):
            if st.button(q, key=f"starter_topic_{i}", icon=":material/arrow_forward:", type="tertiary"):
                st.session_state[QUEUED_PROMPT] = q
                st.rerun()


# ── Flow ──────────────────────────────────────────────────────────────────────


def _load_history(video_id: str, session_id: str) -> bool:
    if state.has_messages(video_id, session_id):
        return True
    try:
        with st.spinner("Loading conversation…"):
            state.set_messages(video_id, session_id, ac.get_messages(session_id, video_id)["messages"])
        return True
    except ApiError as exc:
        st.error(friendly_message(exc))
        if st.button("Try again", key="retry_history"):
            st.rerun()
        return False


def _spinner_text(video_id: str, text: str) -> str:
    looks_like_overview = any(h in text.lower() for h in _OVERVIEW_HINTS)
    if looks_like_overview and state.get_insights(video_id) is None:
        return "Preparing the video summary. The first time can take up to a minute…"
    return "Searching the transcript…"


def _send(video_id: str, session_id: str, text: str, box) -> None:
    """Send one message. The history cache is only updated from the server's reply, so a failed
    or interrupted request can never leave a phantom message behind."""
    state.clear_chat_error()
    with box:
        with st.chat_message("user", avatar=AVATARS["user"]):
            _user_text(text, "pending")
        with st.chat_message("assistant", avatar=AVATARS["assistant"]):
            with st.spinner(_spinner_text(video_id, text)):
                try:
                    resp = ac.chat(video_id, session_id, text)
                except ApiError as exc:
                    state.set_chat_error(video_id, session_id, text, friendly_message(exc), exc.code)
                    st.rerun()
                    return

    answer = dict(resp["assistant_message"])
    answer["standalone_question"] = resp.get("standalone_question")
    answer["_asked"] = text
    answer["sources"] = resp.get("sources") or answer.get("sources") or []
    state.set_messages(video_id, session_id, state.get_messages(video_id, session_id) + [resp["user_message"], answer])
    state.invalidate_sessions(video_id)  # session activity time changed
    st.rerun()


def _render_chat_error(error: dict) -> None:
    """Failed send. "Summary still being prepared" is a wait, not a failure, so it looks like one."""
    if error.get("code") == "SUMMARY_GENERATING":
        st.info(error["message"], icon=":material/hourglass_top:")
    else:
        st.error(error["message"], icon=":material/error:")
    st.caption(f"Not answered: {md_escape(truncate(error['text'], 140))}")
    retry, dismiss, _ = st.columns([1, 1, 3])
    if retry.button("Try again", key="chat_retry", type="primary", width="stretch"):
        st.session_state[QUEUED_PROMPT] = error["text"]
        state.clear_chat_error()
        st.rerun()
    if dismiss.button("Dismiss", key="chat_dismiss", width="stretch"):
        state.clear_chat_error()
        st.rerun()


def render_chat(video: dict, session_id: str) -> None:
    video_id = video["id"]
    if not _load_history(video_id, session_id):
        return

    messages = state.get_messages(video_id, session_id)
    box = st.container(height=HISTORY_HEIGHT, border=True, key="tt-history")
    with box:
        if not messages:
            _render_empty(video_id)
        for i, msg in enumerate(messages):
            _render_message(msg, key=str(msg.get("id") or i))
        error = state.get_chat_error(video_id, session_id)
        if error:
            _render_chat_error(error)

    typed = st.chat_input("Ask about this video…", max_chars=2000)
    queued = st.session_state.pop(QUEUED_PROMPT, None)
    prompt = typed or queued
    if prompt and prompt.strip():
        _send(video_id, session_id, prompt.strip(), box)
