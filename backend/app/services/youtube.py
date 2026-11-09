"""YouTube URL validation, video ID extraction and oEmbed metadata."""
import re
from urllib.parse import parse_qs, urlparse

import requests

from app.core.errors import AppError
from app.schemas.transcript import VideoMetadata

OEMBED_URL = "https://www.youtube.com/oembed"
OEMBED_TIMEOUT_SECONDS = 10

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_PATH_PREFIXES = ("embed", "shorts", "live", "v")


def _invalid_url() -> AppError:
    return AppError("INVALID_VIDEO_URL", "Please provide a valid YouTube URL.", 400)


def extract_video_id(url: str) -> str:
    """Return the 11-character video ID or raise INVALID_VIDEO_URL."""
    if not isinstance(url, str) or not url.strip():
        raise _invalid_url()
    raw = url.strip()
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower()
    except ValueError:
        raise _invalid_url()
    if parsed.scheme not in ("http", "https"):
        raise _invalid_url()

    candidate = None
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in _YOUTUBE_HOSTS:
        parts = [p for p in parsed.path.split("/") if p]
        if parsed.path.rstrip("/") == "/watch":
            candidate = (parse_qs(parsed.query).get("v") or [""])[0]
        elif len(parts) >= 2 and parts[0] in _PATH_PREFIXES:
            candidate = parts[1]

    if not candidate or not _VIDEO_ID_RE.match(candidate):
        raise _invalid_url()
    return candidate


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def fetch_metadata(video_id: str) -> VideoMetadata:
    """Fetch title, channel and thumbnail via YouTube oEmbed (no API key needed)."""
    url = canonical_url(video_id)
    try:
        r = requests.get(
            OEMBED_URL, params={"url": url, "format": "json"}, timeout=OEMBED_TIMEOUT_SECONDS
        )
    except requests.RequestException:
        raise AppError("NETWORK_ERROR", "Could not reach YouTube. Please try again.", 503)
    if r.status_code in (401, 403):
        raise AppError("VIDEO_RESTRICTED", "This video is private or restricted.", 403)
    if r.status_code == 404:
        raise AppError("VIDEO_NOT_FOUND", "This video does not exist or was removed.", 404)
    if not r.ok:
        raise AppError("NETWORK_ERROR", "YouTube returned an unexpected response.", 503)
    try:
        data = r.json()
    except ValueError:
        raise AppError("NETWORK_ERROR", "YouTube returned an unexpected response.", 503)
    return VideoMetadata(
        youtube_video_id=video_id,
        youtube_url=url,
        title=data.get("title"),
        channel_name=data.get("author_name"),
        thumbnail_url=data.get("thumbnail_url"),
    )
