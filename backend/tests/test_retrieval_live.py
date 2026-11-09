"""Real model + real Supabase: embeds, stores and retrieves. Skipped without credentials.

Needs the all-MiniLM-L6-v2 model (downloaded on first use, then cached).
"""
import uuid

import pytest

from app.core.config import get_settings
from app.db.repositories import ChunkRepository, VideoRepository
from app.schemas.chunk import TranscriptChunk
from app.schemas.transcript import VideoMetadata
from app.services.embeddings import EMBEDDING_DIMENSION, embed_query, embed_texts
from app.services.retrieval import retrieve, store_chunks

_s = get_settings()
pytestmark = pytest.mark.skipif(
    not (_s.supabase_url and _s.supabase_key), reason="Supabase credentials not configured"
)

COOKING = [
    "To make the dough, mix flour, water and yeast, then knead for ten minutes.",
    "Bake the bread in a hot oven until the crust turns golden brown.",
]
SPACE = [
    "The rocket engines ignite and the spacecraft lifts off toward orbit around Earth.",
    "Astronauts aboard the station float in microgravity while conducting experiments.",
]


@pytest.fixture
def videos():
    repo = VideoRepository()
    made = []
    for _ in range(2):
        yt = "T" + uuid.uuid4().hex[:10]
        made.append(repo.upsert_from_metadata(VideoMetadata(yt, f"https://www.youtube.com/watch?v={yt}", "t")))
    yield made
    for v in made:
        repo.client.table("videos").delete().eq("id", v["id"]).execute()


def as_chunks(texts):
    return [TranscriptChunk(i, t, i * 30.0, i * 30.0 + 25) for i, t in enumerate(texts)]


def test_real_embedding_dimension_and_normalisation():
    vecs = embed_texts(["hello world", "another sentence"])
    assert len(vecs) == 2 and all(len(v) == EMBEDDING_DIMENSION == 384 for v in vecs)
    assert sum(x * x for x in vecs[0]) == pytest.approx(1.0, abs=1e-3)
    assert len(embed_query("a question")) == 384


def test_semantic_retrieval_is_correct_and_video_scoped(videos):
    cook, space = videos
    assert store_chunks(cook["id"], as_chunks(COOKING)) == 2
    assert store_chunks(space["id"], as_chunks(SPACE)) == 2
    repo = ChunkRepository()
    assert repo.count_for_video(cook["id"]) == 2

    hits = retrieve(cook["id"], "How long should I knead bread dough?", top_k=2)
    assert hits[0].content == COOKING[0]
    assert hits[0].start_time == 0.0 and hits[0].end_time == 25.0
    assert hits[0].similarity >= hits[1].similarity

    # A space question against the cooking video must only ever see cooking chunks.
    wrong = retrieve(cook["id"], "How do astronauts live on the space station?", top_k=5)
    assert {h.content for h in wrong} <= set(COOKING)
    right = retrieve(space["id"], "How do astronauts live on the space station?", top_k=5)
    assert right[0].content == SPACE[1]
    assert wrong[0].similarity < right[0].similarity  # off-topic scores lower

    # Re-storing replaces rather than duplicates.
    store_chunks(cook["id"], as_chunks(COOKING))
    assert repo.count_for_video(cook["id"]) == 2
