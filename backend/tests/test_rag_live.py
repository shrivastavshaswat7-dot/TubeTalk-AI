"""Real Groq + real Supabase + real embeddings. Skipped unless GROQ and Supabase are configured."""
import uuid

import pytest

from app.core.config import get_settings
from app.db.repositories import VideoRepository
from app.prompts.rag import NO_CONTEXT_ANSWER
from app.schemas.chunk import TranscriptChunk
from app.schemas.transcript import VideoMetadata
from app.services.rag import answer_question
from app.services.retrieval import store_chunks

_s = get_settings()


def _set(v: str) -> bool:
    return bool(v) and "your_" not in v


pytestmark = pytest.mark.skipif(
    not (_set(_s.groq_api_key) and _set(_s.groq_model) and _set(_s.supabase_url) and _set(_s.supabase_key)),
    reason="Groq and Supabase credentials not configured",
)

TEXTS = [
    "Today we cover baking bread. First mix 500 grams of flour with 300 millilitres of water and 7 grams of yeast.",
    "Knead the dough for ten minutes until it is smooth and elastic, then let it rise for one hour.",
    "Bake the loaf at 220 degrees Celsius for thirty minutes until the crust is deep golden brown.",
]


@pytest.fixture
def video():
    repo = VideoRepository()
    yt = "T" + uuid.uuid4().hex[:10]
    row = repo.upsert_from_metadata(VideoMetadata(yt, f"https://www.youtube.com/watch?v={yt}", "Bread"))
    store_chunks(row["id"], [TranscriptChunk(i, t, i * 60.0, i * 60.0 + 55) for i, t in enumerate(TEXTS)])
    yield row
    repo.client.table("videos").delete().eq("id", row["id"]).execute()


def test_grounded_answer_with_sources(video):
    out = answer_question(video["id"], "At what temperature should the bread be baked?")
    assert out.grounded
    assert "220" in out.answer
    assert out.sources and out.sources[0].content == TEXTS[2]
    assert out.sources[0].start_time == 120.0


def test_unrelated_question_is_refused_not_invented(video):
    out = answer_question(video["id"], "What is the capital of France?")
    assert out.grounded is False and out.answer == NO_CONTEXT_ANSWER and out.sources == []


def test_related_but_unanswered_question_is_not_invented(video):
    # Same topic as the transcript (so retrieval passes the threshold) but not stated in it.
    out = answer_question(video["id"], "How much salt does the recipe call for?")
    assert "salt" not in out.answer.lower() or out.grounded is False
