"""Video insights routes. GET returns cached insights, generating them on first request."""
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import get_chunk_repo, get_insights_repo, get_video_repo
from app.db.repositories import ChunkRepository, InsightsRepository, VideoRepository
from app.prompts.rag import format_timestamp
from app.schemas.api import (
    InsightsResponse,
    SuggestionsResponse,
    SummaryResponse,
    TakeawaysResponse,
    TopicsResponse,
)
from app.services.insights import get_or_generate
from app.services.suggestions import validated_suggestions

router = APIRouter(prefix="/api/videos/{video_id}", tags=["insights"])


def _topics(row: dict, youtube_url: str) -> list[dict]:
    out = []
    for t in row.get("topics") or []:
        start = t.get("start_time")
        out.append(
            {
                "name": t["name"],
                "start_time": start,
                "timestamp": format_timestamp(start) if start is not None else None,
                "timestamp_url": f"{youtube_url}&t={int(start)}s" if start is not None else None,
            }
        )
    return out


def _load(video_id, videos, insights, chunks, force=False, generate=True):
    vid = str(video_id)
    row, cached = get_or_generate(vid, videos, insights, chunks, force=force, generate=generate)
    return vid, row, cached, videos.get(vid)["youtube_url"]


def _full(vid, row, cached, url):
    return {
        "video_id": vid,
        "cached": cached,
        "insights": {
            "summary": row["summary"],
            "key_takeaways": row["key_takeaways"],
            "topics": _topics(row, url),
            "model": row.get("model"),
            "generated_at": row.get("generated_at"),
        },
    }


# Plain `def` routes run in the threadpool; first-time generation can take a while for long videos.
@router.get("/insights", response_model=InsightsResponse)
def get_insights(
    video_id: UUID,
    videos: VideoRepository = Depends(get_video_repo),
    insights: InsightsRepository = Depends(get_insights_repo),
    chunks: ChunkRepository = Depends(get_chunk_repo),
    generate: bool = True,  # generate=false: only return stored insights (INSIGHTS_NOT_READY if none)
):
    return _full(*_load(video_id, videos, insights, chunks, generate=generate))


@router.post("/insights/regenerate", response_model=InsightsResponse)
def regenerate_insights(
    video_id: UUID,
    videos: VideoRepository = Depends(get_video_repo),
    insights: InsightsRepository = Depends(get_insights_repo),
    chunks: ChunkRepository = Depends(get_chunk_repo),
):
    return _full(*_load(video_id, videos, insights, chunks, force=True))


@router.get("/summary", response_model=SummaryResponse)
def get_summary(
    video_id: UUID,
    videos: VideoRepository = Depends(get_video_repo),
    insights: InsightsRepository = Depends(get_insights_repo),
    chunks: ChunkRepository = Depends(get_chunk_repo),
):
    vid, row, cached, _ = _load(video_id, videos, insights, chunks)
    return {"video_id": vid, "cached": cached, "summary": row["summary"], "generated_at": row.get("generated_at")}


@router.get("/takeaways", response_model=TakeawaysResponse)
def get_takeaways(
    video_id: UUID,
    videos: VideoRepository = Depends(get_video_repo),
    insights: InsightsRepository = Depends(get_insights_repo),
    chunks: ChunkRepository = Depends(get_chunk_repo),
):
    vid, row, cached, _ = _load(video_id, videos, insights, chunks)
    return {
        "video_id": vid, "cached": cached,
        "key_takeaways": row["key_takeaways"], "generated_at": row.get("generated_at"),
    }


@router.get("/topics", response_model=TopicsResponse)
def get_topics(
    video_id: UUID,
    videos: VideoRepository = Depends(get_video_repo),
    insights: InsightsRepository = Depends(get_insights_repo),
    chunks: ChunkRepository = Depends(get_chunk_repo),
):
    vid, row, cached, url = _load(video_id, videos, insights, chunks)
    return {"video_id": vid, "cached": cached, "topics": _topics(row, url), "generated_at": row.get("generated_at")}


@router.get("/suggestions", response_model=SuggestionsResponse)
def get_suggestions(
    video_id: UUID,
    videos: VideoRepository = Depends(get_video_repo),
    insights: InsightsRepository = Depends(get_insights_repo),
    chunks: ChunkRepository = Depends(get_chunk_repo),
):
    """Topic-based starter questions that pass retrieval. Read-only: never generates insights."""
    vid = str(video_id)
    suggestions, ready = validated_suggestions(vid, videos, insights, chunks)
    return {"video_id": vid, "insights_ready": ready, "suggestions": suggestions}
