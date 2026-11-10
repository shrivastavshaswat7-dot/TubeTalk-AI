"""Transcript fetching (youtube-transcript-api 1.x) and cleaning."""
import html
import re

from youtube_transcript_api import (
    AgeRestricted,
    CouldNotRetrieveTranscript,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeTranscriptApi,
)

from app.core.errors import AppError
from app.schemas.transcript import Transcript, TranscriptSegment

# The embedding model (all-MiniLM-L6-v2) is English-centric, so V1 accepts English only.
SUPPORTED_LANGUAGE_PREFIX = "en"

_WS_RE = re.compile(r"\s+")
_NOISE_RE = re.compile(r"^\[[^\]]*\]$|^\([^)]*\)$")  # e.g. [Music], (applause)


def clean_text(text: str) -> str:
    return _WS_RE.sub(" ", html.unescape(text)).strip()


def clean_segments(raw_segments) -> list[TranscriptSegment]:
    """Normalise text, drop empty/noise-only segments, keep timestamps, collapse repeats."""
    cleaned: list[TranscriptSegment] = []
    for seg in raw_segments:
        text = clean_text(seg.text)
        if not text or _NOISE_RE.match(text):
            continue
        if cleaned and cleaned[-1].text == text:  # repeated caption line
            continue
        cleaned.append(
            TranscriptSegment(text=text, start=float(seg.start), duration=float(seg.duration))
        )
    return cleaned


def _pick_transcript(transcript_list):
    """Prefer a manual English transcript, then an auto-generated English one."""
    all_transcripts = list(transcript_list)
    english = [
        t for t in all_transcripts if t.language_code.lower().startswith(SUPPORTED_LANGUAGE_PREFIX)
    ]
    if not english:
        available = sorted({t.language_code for t in all_transcripts})
        raise AppError(
            "UNSUPPORTED_LANGUAGE",
            "Only English transcripts are supported right now. "
            f"Available languages: {', '.join(available) or 'none'}.",
            422,
        )
    english.sort(key=lambda t: t.is_generated)  # manual (False) first
    return english[0]


def fetch_transcript(video_id: str, api: YouTubeTranscriptApi | None = None) -> Transcript:
    api = api or YouTubeTranscriptApi()
    try:
        chosen = _pick_transcript(api.list(video_id))
        fetched = chosen.fetch()
    except AppError:
        raise
    except TranscriptsDisabled:
        raise AppError("TRANSCRIPT_UNAVAILABLE", "Captions are disabled for this video.", 422)
    except NoTranscriptFound:
        raise AppError(
            "TRANSCRIPT_UNAVAILABLE", "No accessible transcript was found for this video.", 422
        )
    except AgeRestricted:
        raise AppError("VIDEO_RESTRICTED", "This video is age-restricted.", 403)
    except (VideoUnavailable, VideoUnplayable):
        raise AppError(
            "VIDEO_RESTRICTED", "This video is unavailable, private or restricted.", 403
        )
    except (RequestBlocked, IpBlocked):
        raise AppError(
            "YOUTUBE_BLOCKED",
            "YouTube blocked the transcript request from this server, so this video couldn't be "
            "processed. Try another video.",
            503,
        )
    except CouldNotRetrieveTranscript:
        raise AppError("TRANSCRIPT_UNAVAILABLE", "The transcript could not be retrieved.", 422)
    except Exception:  # network failures and anything unexpected
        raise AppError("NETWORK_ERROR", "Could not fetch the transcript. Please try again.", 503)

    segments = clean_segments(fetched.snippets)
    if not segments:
        raise AppError("TRANSCRIPT_UNAVAILABLE", "The transcript is empty.", 422)
    return Transcript(
        youtube_video_id=video_id,
        language_code=fetched.language_code,
        is_generated=fetched.is_generated,
        segments=segments,
    )
