from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.db import client as db_client
from app.db.repositories import (
    INSERT_BATCH_SIZE,
    ChunkRepository,
    MessageRepository,
    SessionRepository,
    VideoRepository,
)
from app.schemas.chunk import TranscriptChunk
from app.schemas.transcript import VideoMetadata


def fake_client(data=None, count=None):
    """MagicMock whose any query chain ends in .execute() -> NS(data, count)."""
    client = MagicMock()
    result = NS(data=data if data is not None else [], count=count)
    chain = MagicMock()
    for name in ("select", "insert", "update", "upsert", "delete", "eq", "order", "limit"):
        getattr(chain, name).return_value = chain
    chain.execute.return_value = result
    client.table.return_value = chain
    client.rpc.return_value = chain
    return client, chain


def chunks(n):
    return [TranscriptChunk(i, f"text {i}", i * 10.0, i * 10.0 + 5) for i in range(n)]


# ---------------------------------------------------------------- client


def test_client_not_configured(monkeypatch):
    db_client.get_client.cache_clear()
    monkeypatch.setattr(db_client, "get_settings", lambda: Settings(supabase_url="", supabase_key=""))
    with pytest.raises(AppError) as exc:
        db_client.get_client()
    assert exc.value.error == "DATABASE_NOT_CONFIGURED" and exc.value.status_code == 503
    db_client.get_client.cache_clear()


# ---------------------------------------------------------------- sessions / isolation


def test_session_for_video_ok():
    client, _ = fake_client([{"id": "s1", "video_id": "v1"}])
    assert SessionRepository(client).get_for_video("s1", "v1")["id"] == "s1"


def test_session_not_found():
    client, _ = fake_client([])
    with pytest.raises(AppError) as exc:
        SessionRepository(client).get_for_video("s1", "v1")
    assert exc.value.error == "SESSION_NOT_FOUND" and exc.value.status_code == 404


def test_session_video_mismatch():
    client, _ = fake_client([{"id": "s1", "video_id": "OTHER"}])
    with pytest.raises(AppError) as exc:
        SessionRepository(client).get_for_video("s1", "v1")
    assert exc.value.error == "SESSION_VIDEO_MISMATCH"


def test_session_delete_only_touches_sessions_table():
    client, _ = fake_client([{"id": "s1"}])
    assert SessionRepository(client).delete("s1") is True
    client.table.assert_called_once_with("chat_sessions")


# ---------------------------------------------------------------- messages


def test_messages_scoped_to_session_and_limit_returns_chronological():
    rows_desc = [{"id": 3}, {"id": 2}]  # newest first from the DB
    client, chain = fake_client(rows_desc)
    out = MessageRepository(client).list_for_session("s1", limit=2)
    assert [r["id"] for r in out] == [2, 3]
    chain.eq.assert_called_with("session_id", "s1")


def test_message_add_persists_sources():
    client, chain = fake_client([{"id": "m1"}])
    src = [{"chunk_id": "c1", "start_time": 1.0}]
    MessageRepository(client).add("s1", "assistant", "hi", sources=src)
    row = chain.insert.call_args.args[0]
    assert row == {"session_id": "s1", "role": "assistant", "content": "hi", "sources": src}


# ---------------------------------------------------------------- chunks


def test_insert_many_batches_and_row_shape():
    client, chain = fake_client()
    n = INSERT_BATCH_SIZE * 2 + 1
    emb = [[0.1] * 384 for _ in range(n)]
    assert ChunkRepository(client).insert_many("v1", chunks(n), emb) == n
    assert chain.insert.call_count == 3
    first = chain.insert.call_args_list[0].args[0][0]
    assert first["video_id"] == "v1" and first["chunk_index"] == 0
    assert first["start_time"] == 0.0 and len(first["embedding"]) == 384


def test_insert_many_embedding_length_mismatch():
    client, _ = fake_client()
    with pytest.raises(ValueError):
        ChunkRepository(client).insert_many("v1", chunks(3), [[0.0] * 384])


def test_match_always_passes_video_id_and_requires_it():
    client, _ = fake_client([{"id": "c1", "similarity": 0.9}])
    repo = ChunkRepository(client)
    out = repo.match("v1", [0.0] * 384, k=3)
    assert out[0]["id"] == "c1"
    name, params = client.rpc.call_args.args
    assert name == "match_transcript_chunks"
    assert params["p_video_id"] == "v1" and params["match_count"] == 3
    with pytest.raises(ValueError):
        repo.match("", [0.0] * 384)


def test_count_for_video():
    client, _ = fake_client([], count=7)
    assert ChunkRepository(client).count_for_video("v1") == 7


# ---------------------------------------------------------------- videos + error mapping


def test_video_upsert_uses_youtube_id_conflict_key():
    client, chain = fake_client([{"id": "v1"}])
    meta = VideoMetadata("abc12345678", "https://www.youtube.com/watch?v=abc12345678", "T", "C", "th")
    VideoRepository(client).upsert_from_metadata(meta, status="processing")
    assert chain.upsert.call_args.kwargs == {"on_conflict": "youtube_video_id"}
    row = chain.upsert.call_args.args[0]
    assert row["youtube_video_id"] == "abc12345678" and row["processing_status"] == "processing"


def test_database_failures_become_database_error():
    client = MagicMock()
    client.table.side_effect = RuntimeError("connection refused: secret-host")
    with pytest.raises(AppError) as exc:
        VideoRepository(client).get("v1")
    assert exc.value.error == "DATABASE_ERROR" and exc.value.status_code == 503
    assert "secret-host" not in exc.value.message
