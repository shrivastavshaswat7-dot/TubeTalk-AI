"""session_state helpers and query-param sync.

Messages are cached per (video_id, session_id) and sessions per video_id, so one video's or
session's data can never be shown under another.
"""
import time

import streamlit as st

KEY_VIDEO = "video"  # open video dict, or None
KEY_SESSION_ID = "session_id"  # open session id, or None
KEY_PLAYER_START = "player_start"  # seconds the player should start at
KEY_PLAYER_SEEK = "player_seek"  # counts explicit seeks; part of the player's key so each one remounts it
KEY_RECENT = "recent_videos"  # cached list of completed videos
KEY_HEALTH = "health_cache"  # (checked_at, healthy, detail)
KEY_FLASH = "flash_message"  # one-shot toast shown on the next run
KEY_CHAT_ERROR = "chat_error"  # last failed chat attempt, kept until resolved

HEALTH_TTL_SECONDS = 20


def init_state() -> None:
    for key, default in [
        (KEY_VIDEO, None),
        (KEY_SESSION_ID, None),
        (KEY_PLAYER_START, 0),
        (KEY_PLAYER_SEEK, 0),
        (KEY_RECENT, None),
        (KEY_HEALTH, None),
        (KEY_FLASH, None),
        (KEY_CHAT_ERROR, None),
    ]:
        st.session_state.setdefault(key, default)


# ── Open video / session ──────────────────────────────────────────────────────


def get_video() -> dict | None:
    return st.session_state.get(KEY_VIDEO)


def get_session_id() -> str | None:
    return st.session_state.get(KEY_SESSION_ID)


def open_workspace(video: dict, session_id: str) -> None:
    """Make (video, session) the active pair and mirror it into the URL so a refresh restores it."""
    previous = (get_video() or {}).get("id")
    st.session_state[KEY_VIDEO] = video
    st.session_state[KEY_SESSION_ID] = session_id
    if previous != video["id"]:
        st.session_state[KEY_PLAYER_START] = 0
        st.session_state[KEY_PLAYER_SEEK] = 0  # a newly opened video does not autoplay
    st.session_state[KEY_CHAT_ERROR] = None
    st.query_params["video"] = video["id"]
    st.query_params["session"] = session_id


def switch_session(session_id: str) -> None:
    video = get_video()
    st.session_state[KEY_SESSION_ID] = session_id
    st.session_state[KEY_CHAT_ERROR] = None
    if video:
        st.query_params["video"] = video["id"]
        st.query_params["session"] = session_id


def close_workspace() -> None:
    st.session_state[KEY_VIDEO] = None
    st.session_state[KEY_SESSION_ID] = None
    st.session_state[KEY_CHAT_ERROR] = None
    st.query_params.clear()


def read_query_params() -> tuple[str | None, str | None]:
    return st.query_params.get("video"), st.query_params.get("session")


# ── Messages (keyed by video AND session) ─────────────────────────────────────


def messages_key(video_id: str, session_id: str) -> str:
    return f"messages_{video_id}_{session_id}"


def has_messages(video_id: str, session_id: str) -> bool:
    return messages_key(video_id, session_id) in st.session_state


def get_messages(video_id: str, session_id: str) -> list:
    return st.session_state.get(messages_key(video_id, session_id), [])


def set_messages(video_id: str, session_id: str, messages: list) -> None:
    st.session_state[messages_key(video_id, session_id)] = messages


def clear_messages(video_id: str, session_id: str) -> None:
    st.session_state.pop(messages_key(video_id, session_id), None)


# ── Sessions per video ────────────────────────────────────────────────────────


def sessions_key(video_id: str) -> str:
    return f"sessions_{video_id}"


def get_sessions(video_id: str) -> list | None:
    return st.session_state.get(sessions_key(video_id))


def set_sessions(video_id: str, sessions: list) -> None:
    st.session_state[sessions_key(video_id)] = sessions


def invalidate_sessions(video_id: str) -> None:
    st.session_state.pop(sessions_key(video_id), None)


# ── Insights per video ────────────────────────────────────────────────────────


def insights_key(video_id: str) -> str:
    return f"insights_{video_id}"


def get_insights(video_id: str):
    return st.session_state.get(insights_key(video_id))


def set_insights(video_id: str, data) -> None:
    st.session_state[insights_key(video_id)] = data
    invalidate_suggestions(video_id)  # suggestions are derived from the insights' topics


# ── Validated starter suggestions per video ───────────────────────────────────


def suggestions_key(video_id: str) -> str:
    return f"suggestions_{video_id}"


def get_suggestions(video_id: str) -> list | None:
    return st.session_state.get(suggestions_key(video_id))


def set_suggestions(video_id: str, suggestions: list) -> None:
    st.session_state[suggestions_key(video_id)] = suggestions


def invalidate_suggestions(video_id: str) -> None:
    st.session_state.pop(suggestions_key(video_id), None)


# ── Player ────────────────────────────────────────────────────────────────────


def get_player_start() -> int:
    return int(st.session_state.get(KEY_PLAYER_START) or 0)


def set_player_start(seconds: float) -> None:
    """An explicit seek. The YouTube iframe only reloads when its src changes, so asking for the same
    time again would do nothing; bumping the counter gives the player a new key and remounts it."""
    st.session_state[KEY_PLAYER_START] = int(seconds)
    st.session_state[KEY_PLAYER_SEEK] = get_player_seek() + 1


def get_player_seek() -> int:
    return int(st.session_state.get(KEY_PLAYER_SEEK) or 0)


# ── Short-lived caches so reruns do not hammer the backend ────────────────────


def get_recent_videos() -> list | None:
    return st.session_state.get(KEY_RECENT)


def set_recent_videos(videos: list) -> None:
    st.session_state[KEY_RECENT] = videos


def invalidate_recent_videos() -> None:
    st.session_state[KEY_RECENT] = None


def cached_health(fetch) -> tuple[bool, str]:
    """Health check at most once per HEALTH_TTL_SECONDS (a down backend would otherwise slow every rerun)."""
    entry = st.session_state.get(KEY_HEALTH)
    now = time.time()
    if entry and now - entry[0] < HEALTH_TTL_SECONDS:
        return entry[1], entry[2]
    healthy, detail = fetch()
    st.session_state[KEY_HEALTH] = (now, healthy, detail)
    return healthy, detail


def invalidate_health() -> None:
    st.session_state[KEY_HEALTH] = None


# ── One-shot messages and chat errors ─────────────────────────────────────────


def flash(message: str) -> None:
    """Show a toast on the next run (a toast issued right before st.rerun() would be lost)."""
    st.session_state[KEY_FLASH] = message


def pop_flash() -> str | None:
    message = st.session_state.get(KEY_FLASH)
    st.session_state[KEY_FLASH] = None
    return message


def set_chat_error(video_id: str, session_id: str, text: str, message: str, code: str = "") -> None:
    st.session_state[KEY_CHAT_ERROR] = {
        "video_id": video_id,
        "session_id": session_id,
        "text": text,
        "message": message,
        "code": code,
    }


def get_chat_error(video_id: str, session_id: str) -> dict | None:
    err = st.session_state.get(KEY_CHAT_ERROR)
    if err and err["video_id"] == video_id and err["session_id"] == session_id:
        return err
    return None


def clear_chat_error() -> None:
    st.session_state[KEY_CHAT_ERROR] = None
