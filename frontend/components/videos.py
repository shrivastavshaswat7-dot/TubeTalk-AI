"""Shared video helpers used by Home and the sidebar."""
import api_client as ac
import state
from api_client import ApiError


def load_recent_videos(force: bool = False) -> list[dict]:
    """Completed videos, newest first. Cached in session_state; failed/unfinished ones are hidden.
    Raises ApiError if the backend can't be reached and nothing is cached."""
    cached = state.get_recent_videos()
    if cached is not None and not force:
        return cached
    resp = ac.list_videos()
    videos = [v for v in resp.get("videos", []) if v.get("processing_status") == "completed"]
    state.set_recent_videos(videos)
    return videos


def latest_session_id(video_id: str) -> str:
    """Most recently active session of a video, creating one if the video has none."""
    sessions = ac.list_sessions(video_id).get("sessions", [])
    if sessions:
        state.set_sessions(video_id, sessions)
        return sessions[0]["id"]
    state.invalidate_sessions(video_id)
    return ac.create_session(video_id)["session"]["id"]


def open_video(video: dict) -> None:
    """Open a video in its most recent session. Raises ApiError; the caller shows it and navigates."""
    state.open_workspace(video, latest_session_id(video["id"]))


__all__ = ["load_recent_videos", "latest_session_id", "open_video", "ApiError"]
