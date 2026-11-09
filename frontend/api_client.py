"""All HTTP calls to the FastAPI backend live here. Nothing else in the frontend touches the network."""
import requests

from config import get_api_base_url

# Seconds. Processing and first-time insights are synchronous on the backend and can take minutes.
_T_DEFAULT = 15
_T_HEALTH = 5
_T_PROCESS = 300
_T_CHAT = 300  # an overview question may generate the video's insights the first time
_T_INSIGHTS = 300


class ApiError(Exception):
    """Any failed backend call. `code` is the backend's error code, or a client-side one
    (BACKEND_UNREACHABLE, TIMEOUT, HTTP_ERROR)."""

    def __init__(self, code: str, message: str, status: int = 0):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _error_from_response(resp: requests.Response) -> ApiError:
    """Backend errors look like {"success": false, "error": CODE, "message": text}."""
    try:
        body = resp.json()
        return ApiError(body.get("error", "HTTP_ERROR"), body.get("message", resp.reason or ""), resp.status_code)
    except ValueError:
        return ApiError("HTTP_ERROR", resp.reason or "Unknown error", resp.status_code)


def _request(method: str, path: str, timeout: int = _T_DEFAULT, **kwargs) -> dict:
    try:
        resp = requests.request(method, f"{get_api_base_url()}{path}", timeout=timeout, **kwargs)
    except requests.Timeout:
        raise ApiError("TIMEOUT", "This is taking longer than expected. Please try again.")
    except requests.RequestException:
        raise ApiError("BACKEND_UNREACHABLE", "Cannot reach the TubeTalk backend.")
    if not resp.ok:
        raise _error_from_response(resp)
    try:
        return resp.json()
    except ValueError:
        raise ApiError("HTTP_ERROR", "The backend returned an unreadable response.", resp.status_code)


# ── Public API ────────────────────────────────────────────────────────────────


def check_health() -> tuple[bool, str]:
    """Return (is_healthy, detail). Never raises."""
    try:
        r = requests.get(f"{get_api_base_url()}/health", timeout=_T_HEALTH)
        r.raise_for_status()
        data = r.json()
        return data.get("status") == "healthy", data.get("application", "")
    except (requests.RequestException, ValueError) as exc:
        return False, type(exc).__name__


def process_video(youtube_url: str) -> dict:
    return _request("POST", "/api/videos/process", _T_PROCESS, json={"youtube_url": youtube_url})


def list_videos() -> dict:
    return _request("GET", "/api/videos")


def get_video(video_id: str) -> dict:
    return _request("GET", f"/api/videos/{video_id}")


def list_sessions(video_id: str) -> dict:
    return _request("GET", f"/api/videos/{video_id}/sessions")


def create_session(video_id: str, title: str | None = None) -> dict:
    body = {"video_id": video_id}
    if title:
        body["session_title"] = title
    return _request("POST", "/api/sessions", json=body)


def get_messages(session_id: str, video_id: str) -> dict:
    return _request("GET", f"/api/sessions/{session_id}/messages", params={"video_id": video_id})


def delete_session(session_id: str, video_id: str) -> dict:
    return _request("DELETE", f"/api/sessions/{session_id}", params={"video_id": video_id})


def chat(video_id: str, session_id: str, message: str) -> dict:
    return _request(
        "POST",
        "/api/chat",
        _T_CHAT,
        json={"video_id": video_id, "session_id": session_id, "message": message},
    )


def get_insights(video_id: str, generate: bool = True) -> dict:
    """generate=False only reads stored insights (raises INSIGHTS_NOT_READY if there are none)."""
    if generate:
        return _request("GET", f"/api/videos/{video_id}/insights", _T_INSIGHTS)
    return _request("GET", f"/api/videos/{video_id}/insights", params={"generate": "false"})


def get_suggestions(video_id: str) -> dict:
    """Topic starter questions already validated against the transcript (never generates insights)."""
    return _request("GET", f"/api/videos/{video_id}/suggestions")


def regenerate_insights(video_id: str) -> dict:
    return _request("POST", f"/api/videos/{video_id}/insights/regenerate", _T_INSIGHTS)
