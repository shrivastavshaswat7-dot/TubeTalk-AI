"""Answer whole-video questions from the stored Insights, without another LLM call.

The text is exactly the stored summary / takeaways / topics. Sources are never invented:
- one "summary" source says the answer came from the transcript-derived summary;
- each topic with a validated timestamp is mapped to the stored transcript chunk that actually
  contains that moment, and that chunk's real id, times and text become the source. Topics without
  a timestamp, or whose time falls in no chunk, get no source and no timestamp in the text.
"""
from app.prompts.rag import format_timestamp
from app.services.question_intent import POINTS


def _timestamp_url(youtube_url: str, seconds: float) -> str:
    sep = "&" if "?" in youtube_url else "?"
    return f"{youtube_url}{sep}t={int(seconds)}s"


def chunk_at(chunks: list[dict], seconds: float) -> dict | None:
    """The stored chunk containing `seconds`; with overlapping chunks, the one starting latest."""
    containing = [
        c for c in chunks
        if c.get("start_time") is not None and c.get("end_time") is not None
        and c["start_time"] <= seconds <= c["end_time"]
    ]
    return max(containing, key=lambda c: c["start_time"]) if containing else None


def build_summary_answer(intent: str, insights: dict, chunks: list[dict], youtube_url: str) -> tuple[str, list[dict]]:
    """Return (answer_markdown, sources) built only from stored insights and stored chunks."""
    sources: list[dict] = [{
        "kind": "summary",
        "topic": None,
        "chunk_id": None,
        "chunk_index": None,
        "content": "",
        "start_time": None,
        "end_time": None,
        "similarity": None,
        "timestamp_url": None,
    }]
    topic_lines = []
    for topic in insights.get("topics") or []:
        name = (topic.get("name") or "").strip()
        if not name:
            continue
        start = topic.get("start_time")
        chunk = chunk_at(chunks, start) if isinstance(start, (int, float)) else None
        if chunk is None:
            topic_lines.append(f"- {name}")
            continue
        topic_lines.append(f"- [{format_timestamp(start)}] {name}")
        sources.append({
            "kind": "topic",
            "topic": name,
            "chunk_id": chunk.get("id"),
            "chunk_index": chunk.get("chunk_index"),
            "content": chunk.get("content", ""),
            "start_time": float(start),  # the topic's validated start, inside this chunk
            "end_time": chunk.get("end_time"),
            "similarity": None,  # not a similarity match
            "timestamp_url": _timestamp_url(youtube_url, start),
        })

    if intent == POINTS:
        points = "\n".join(f"- {t}" for t in insights.get("key_takeaways") or [])
        answer = f"**Key points**\n\n{points}"
        if topic_lines:
            answer += "\n\n**Topics in the video**\n\n" + "\n".join(topic_lines)
    else:
        answer = (insights.get("summary") or "").strip()
        if topic_lines:
            answer += "\n\n**Topics covered**\n\n" + "\n".join(topic_lines)
    return answer, sources
