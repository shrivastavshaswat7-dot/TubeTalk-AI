from unittest.mock import MagicMock

import pytest

from app.core.errors import AppError
from app.schemas.chunk import TranscriptChunk
from app.services import embeddings
from app.services.embeddings import EMBEDDING_DIMENSION, embed_query, embed_texts
from app.services.retrieval import retrieve, store_chunks


def fake_model(dim=EMBEDDING_DIMENSION):
    m = MagicMock()
    m.encode.side_effect = lambda texts, **kw: [[0.5] * dim for _ in texts]
    return m


def chunks(n):
    return [TranscriptChunk(i, f"text {i}", i * 10.0, i * 10.0 + 5) for i in range(n)]


# ---------------------------------------------------------------- embeddings


def test_embed_texts_shape_and_options():
    m = fake_model()
    out = embed_texts(["a", "b", "c"], model=m)
    assert len(out) == 3 and all(len(v) == EMBEDDING_DIMENSION for v in out)
    kwargs = m.encode.call_args.kwargs
    assert kwargs["normalize_embeddings"] is True and kwargs["batch_size"] == embeddings.BATCH_SIZE


def test_embed_empty_list_returns_empty():
    assert embed_texts([], model=fake_model()) == []


@pytest.mark.parametrize("bad", [[""], ["ok", "   "], [None]])
def test_embed_rejects_empty_text(bad):
    with pytest.raises(AppError) as exc:
        embed_texts(bad, model=fake_model())
    assert exc.value.error == "EMBEDDING_ERROR"


def test_wrong_dimension_is_an_error():
    with pytest.raises(AppError) as exc:
        embed_texts(["a"], model=fake_model(dim=10))
    assert exc.value.error == "EMBEDDING_ERROR" and "384" in exc.value.message


def test_model_failure_is_mapped_without_leaking_details():
    m = MagicMock()
    m.encode.side_effect = RuntimeError("CUDA secret detail")
    with pytest.raises(AppError) as exc:
        embed_query("hi", model=m)
    assert exc.value.error == "EMBEDDING_ERROR" and "secret" not in exc.value.message


def test_model_load_failure_is_mapped(monkeypatch):
    embeddings.get_model.cache_clear()
    monkeypatch.setattr("app.services.embeddings.get_settings", lambda: MagicMock(embedding_model="nope/does-not-exist"))
    with pytest.raises(AppError) as exc:
        embeddings.get_model()
    assert exc.value.error == "EMBEDDING_ERROR"
    embeddings.get_model.cache_clear()


# ---------------------------------------------------------------- store_chunks


def test_store_chunks_embeds_then_replaces_existing():
    repo = MagicMock()
    repo.insert_many.return_value = 3
    assert store_chunks("v1", chunks(3), chunk_repo=repo, model=fake_model()) == 3
    repo.delete_for_video.assert_called_once_with("v1")
    _, cs, embs = repo.insert_many.call_args.args
    assert len(cs) == len(embs) == 3 and len(embs[0]) == EMBEDDING_DIMENSION


def test_store_chunks_embedding_failure_does_not_touch_db():
    repo = MagicMock()
    m = MagicMock()
    m.encode.side_effect = RuntimeError("boom")
    with pytest.raises(AppError):
        store_chunks("v1", chunks(2), chunk_repo=repo, model=m)
    repo.delete_for_video.assert_not_called()
    repo.insert_many.assert_not_called()


def test_store_chunks_cleans_up_partial_data_on_db_failure():
    repo = MagicMock()
    repo.insert_many.side_effect = AppError("DATABASE_ERROR", "x", 503)
    with pytest.raises(AppError):
        store_chunks("v1", chunks(2), chunk_repo=repo, model=fake_model())
    assert repo.delete_for_video.call_count == 2  # before insert + cleanup after failure


def test_store_chunks_empty_input():
    with pytest.raises(AppError) as exc:
        store_chunks("v1", [], chunk_repo=MagicMock(), model=fake_model())
    assert exc.value.error == "TRANSCRIPT_UNAVAILABLE"


# ---------------------------------------------------------------- retrieve


def test_retrieve_is_video_scoped_and_maps_rows():
    repo = MagicMock()
    repo.match.return_value = [
        {"id": "c1", "chunk_index": 4, "content": "hello", "start_time": 1.0, "end_time": 2.0, "similarity": 0.83}
    ]
    out = retrieve("v1", "what?", top_k=3, chunk_repo=repo, model=fake_model())
    video_id, vec, k = repo.match.call_args.args
    assert video_id == "v1" and k == 3 and len(vec) == EMBEDDING_DIMENSION
    assert out[0].chunk_id == "c1" and out[0].similarity == 0.83 and out[0].start_time == 1.0


def test_retrieve_default_top_k_from_settings():
    repo = MagicMock()
    repo.match.return_value = []
    assert retrieve("v1", "q", chunk_repo=repo, model=fake_model()) == []
    assert repo.match.call_args.args[2] == 5


@pytest.mark.parametrize("video_id,question,code", [("", "q", "INVALID_VIDEO_ID"), ("v1", "  ", "EMPTY_MESSAGE")])
def test_retrieve_validation(video_id, question, code):
    with pytest.raises(AppError) as exc:
        retrieve(video_id, question, chunk_repo=MagicMock(), model=fake_model())
    assert exc.value.error == code
