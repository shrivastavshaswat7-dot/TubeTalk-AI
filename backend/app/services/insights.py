"""Video insights: summary, key takeaways and topics from the FULL transcript.

Short transcripts go to the model in one pass. Long ones use map-reduce: each ~10k-character
section is condensed into notes (map), notes are merged until they fit (reduce), and a final call
returns the JSON insights. Results are cached in Supabase (table video_insights).
"""
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.repositories import ChunkRepository, InsightsRepository, VideoRepository
from app.prompts.insights import (
    CONDENSE_SYSTEM_PROMPT,
    FINAL_SYSTEM_PROMPT,
    JSON_RETRY_REMINDER,
    MAP_SYSTEM_PROMPT,
)
from app.prompts.rag import format_timestamp
from app.services import llm

SINGLE_PASS_MAX_CHARS = 20_000  # whole transcript in one call up to ~5k tokens
SECTION_CHARS = 10_000  # size of one map input
REDUCE_MAX_CHARS = 14_000  # notes must fit under this before the final call
MAX_REDUCE_ROUNDS = 5
RATE_LIMIT_WAITS = (5, 15, 30)  # seconds to wait before each retry after a Groq rate limit
GENERATING_STALE_AFTER = timedelta(minutes=10)  # a crashed run must not block a video forever

MAX_TAKEAWAYS, MAX_TAKEAWAY_CHARS = 10, 300
MAX_TOPICS, MAX_TOPIC_NAME_CHARS = 10, 100

_TS_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$")


@dataclass(frozen=True)
class InsightsData:
    summary: str
    key_takeaways: list[str]
    topics: list[dict]  # [{"name": str, "start_time": float | None}]


# ------------------------------------------------------------------ transcript text


def chunks_to_text(chunks: list[dict]) -> str:
    """One line per chunk, prefixed with its [mm:ss] start so the model can cite times."""
    return "\n".join(f"[{format_timestamp(c.get('start_time') or 0)}] {c['content']}" for c in chunks)


def split_sections(chunks: list[dict], max_chars: int = SECTION_CHARS) -> list[list[dict]]:
    sections, current, size = [], [], 0
    for c in chunks:
        if current and size + len(c["content"]) > max_chars:
            sections.append(current)
            current, size = [], 0
        current.append(c)
        size += len(c["content"])
    if current:
        sections.append(current)
    return sections


# ------------------------------------------------------------------ LLM calls


def _generate(system: str, user: str, llm_client, sleep) -> str:
    """One LLM call; waits and retries when Groq rate-limits (free tier has tight token limits)."""
    for wait in (*RATE_LIMIT_WAITS, None):
        try:
            return llm.generate(system, user, llm=llm_client)
        except AppError as exc:
            if exc.error != "LLM_RATE_LIMITED" or wait is None:
                raise
            sleep(wait)
    raise AssertionError("unreachable")


def parse_timestamp(value, max_seconds: float) -> float | None:
    """'mm:ss' or 'h:mm:ss' -> seconds. Returns None if malformed or outside the video."""
    if not isinstance(value, str):
        return None
    m = _TS_RE.match(value.strip().strip("[]"))
    if not m:
        return None
    h, mnt, sec = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
    if sec > 59:
        return None
    total = float(h * 3600 + mnt * 60 + sec)
    return total if total <= max_seconds + 60 else None


def parse_insights(reply: str, max_seconds: float) -> InsightsData:
    """Validate the model's JSON. Raises ValueError if it is unusable."""
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object")
    data = json.loads(reply[start : end + 1])

    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("missing summary")

    raw_takeaways = data.get("key_takeaways")
    if not isinstance(raw_takeaways, list):
        raise ValueError("takeaways must be a list")
    takeaways = [t.strip()[:MAX_TAKEAWAY_CHARS] for t in raw_takeaways if isinstance(t, str) and t.strip()]
    if not takeaways:
        raise ValueError("no takeaways")

    raw_topics = data.get("topics")
    if not isinstance(raw_topics, list):
        raise ValueError("topics must be a list")
    topics = []
    for t in raw_topics:
        if isinstance(t, dict) and isinstance(t.get("name"), str) and t["name"].strip():
            topics.append(
                {
                    "name": t["name"].strip()[:MAX_TOPIC_NAME_CHARS],
                    "start_time": parse_timestamp(t.get("timestamp"), max_seconds),
                }
            )
    if not topics:
        raise ValueError("no topics")

    return InsightsData(summary.strip(), takeaways[:MAX_TAKEAWAYS], topics[:MAX_TOPICS])


# ------------------------------------------------------------------ generation


def generate_insights(chunks: list[dict], llm_client=None, sleep=time.sleep) -> InsightsData:
    if not chunks:
        raise AppError("TRANSCRIPT_UNAVAILABLE", "There is no transcript to analyse.", 422)
    max_seconds = max((c.get("end_time") or c.get("start_time") or 0) for c in chunks)

    material = chunks_to_text(chunks)
    if len(material) > SINGLE_PASS_MAX_CHARS:
        # Map: condense each section of the transcript into notes.
        notes = []
        for i, section in enumerate(split_sections(chunks), 1):
            span = f"{format_timestamp(section[0].get('start_time'))}-{format_timestamp(section[-1].get('end_time'))}"
            text = _generate(MAP_SYSTEM_PROMPT, chunks_to_text(section), llm_client, sleep)
            notes.append(f"Part {i} ({span}):\n{text}")
        # Reduce: merge notes until they fit in one final call.
        for _ in range(MAX_REDUCE_ROUNDS):
            material = "\n\n".join(notes)
            if len(material) <= REDUCE_MAX_CHARS:
                break
            notes = _condense(notes, llm_client, sleep)
        else:
            material = "\n\n".join(notes)
            if len(material) > REDUCE_MAX_CHARS:
                raise AppError("INSIGHTS_FAILED", "The transcript is too long to analyse.", 500)

    # Final: JSON insights (one retry if the model's JSON is unusable).
    reply = _generate(FINAL_SYSTEM_PROMPT, material, llm_client, sleep)
    try:
        return parse_insights(reply, max_seconds)
    except (ValueError, json.JSONDecodeError):
        reply = _generate(FINAL_SYSTEM_PROMPT, material + JSON_RETRY_REMINDER, llm_client, sleep)
        try:
            return parse_insights(reply, max_seconds)
        except (ValueError, json.JSONDecodeError):
            raise AppError("INSIGHTS_FAILED", "Could not generate insights for this video. Please try again.", 500)


def _condense(notes: list[str], llm_client, sleep) -> list[str]:
    groups, current, size = [], [], 0
    for n in notes:
        if current and size + len(n) > SECTION_CHARS:
            groups.append(current)
            current, size = [], 0
        current.append(n)
        size += len(n)
    if current:
        groups.append(current)
    return [_generate(CONDENSE_SYSTEM_PROMPT, "\n\n".join(g), llm_client, sleep) for g in groups]


# ------------------------------------------------------------------ caching


def _is_stale(row: dict) -> bool:
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(row["updated_at"]) > GENERATING_STALE_AFTER
    except (KeyError, TypeError, ValueError):
        return True


def get_or_generate(
    video_id: str,
    videos: VideoRepository,
    insights: InsightsRepository,
    chunks: ChunkRepository,
    force: bool = False,
    llm_client=None,
    sleep=time.sleep,
    generate: bool = True,
) -> tuple[dict, bool]:
    """Return (insights_row, was_cached). Generates and stores them if missing (or force=True).
    With generate=False it only reads: INSIGHTS_NOT_READY (404) if nothing is stored yet."""
    video = videos.get(video_id)
    if video is None:
        raise AppError("VIDEO_NOT_FOUND", "The requested video does not exist.", 404)
    if video["processing_status"] != "completed":
        raise AppError("VIDEO_NOT_READY", "This video has not finished processing.", 409)

    row = insights.get(video_id)
    if row and row["status"] == "completed" and row.get("summary") and not force:
        return row, True
    if row and row["status"] == "generating" and not _is_stale(row):
        raise AppError("INSIGHTS_GENERATING", "Insights are already being generated. Please wait.", 409)
    if not generate:
        raise AppError("INSIGHTS_NOT_READY", "Insights have not been generated for this video yet.", 404)

    insights.mark_generating(video_id)
    try:
        data = generate_insights(chunks.list_for_video(video_id), llm_client=llm_client, sleep=sleep)
    except AppError as exc:
        insights.save_failed(video_id, exc.message)
        raise
    except Exception:
        insights.save_failed(video_id, "Insight generation failed unexpectedly.")
        raise AppError("INSIGHTS_FAILED", "Could not generate insights for this video. Please try again.", 500)

    saved = insights.save_completed(
        video_id, data.summary, data.key_takeaways, data.topics, get_settings().groq_model
    )
    return saved, False
