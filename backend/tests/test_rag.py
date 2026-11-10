from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import groq
import httpx
import pytest

from app.core.errors import AppError
from app.prompts.rag import INSUFFICIENT_MARKER, NO_CONTEXT_ANSWER, build_context, format_timestamp
from app.schemas.chunk import RetrievedChunk
from app.services import llm
from app.services.embeddings import EMBEDDING_DIMENSION
from app.services.rag import answer_question


def rc(i, sim, start=10.0, end=40.0, text=None):
    return RetrievedChunk(f"c{i}", i, text or f"chunk text {i}", start, end, sim)


def repo_returning(chunks):
    """Fake chunk repo: the video's chunks (list_for_video) and similarity search (match, best first)."""
    rows = [{"id": c.chunk_id, "chunk_index": c.chunk_index, "content": c.content,
             "start_time": c.start_time, "end_time": c.end_time, "similarity": c.similarity} for c in chunks]
    repo = MagicMock()
    repo.list_for_video.return_value = [{k: v for k, v in r.items() if k != "similarity"} for r in rows]
    repo.match.side_effect = lambda video_id, emb, k: sorted(rows, key=lambda r: -r["similarity"])[:k]
    return repo


def fake_model():
    m = MagicMock()
    m.encode.side_effect = lambda texts, **kw: [[0.1] * EMBEDDING_DIMENSION for _ in texts]
    return m


def fake_llm(text="The answer is X [C1]."):
    m = MagicMock()
    m.invoke.return_value = NS(content=text)
    return m


def run(chunks, reply="The answer is X [C1].", **kw):
    client = fake_llm(reply)
    out = answer_question("v1", "what?", chunk_repo=repo_returning(chunks), model=fake_model(), llm_client=client, **kw)
    return out, client


def prompt_of(client):
    system, user = client.invoke.call_args.args[0]
    return system.content, user.content


# ---------------------------------------------------------------- prompt helpers


@pytest.mark.parametrize("sec,expected", [(0, "00:00"), (275.9, "04:35"), (3725, "1:02:05"), (None, "??:??")])
def test_format_timestamp(sec, expected):
    assert format_timestamp(sec) == expected


def test_build_context_numbers_excerpts_with_timestamps():
    ctx = build_context([rc(1, 0.9, 275, 300, "supervised learning"), rc(2, 0.1, 300, 320, "next")])
    assert "[C1] (04:35 - 05:00)\nsupervised learning" in ctx and "[C2] (05:00 - 05:20)\nnext" in ctx


# ---------------------------------------------------------------- context selection


def test_short_transcript_is_passed_whole_in_video_order():
    chunks = [rc(2, 0.9, 50, 80, "gamma"), rc(1, 0.1, 10, 40, "alpha"), rc(3, 0.02, 80, 99, "omega")]
    out, client = run(chunks)
    assert out.mode == "full"
    system, user = prompt_of(client)
    assert "ONLY" in system and "[C2]" in system  # citation instructions
    # every chunk is context, numbered in video order (not similarity order)
    assert user.index("[C1] (00:10") < user.index("[C2] (00:50") < user.index("[C3] (01:20")
    assert "alpha" in user and "omega" in user and "Current question: what?" in user


def test_long_transcript_uses_top_k_most_similar(monkeypatch):
    monkeypatch.setattr("app.services.rag.get_settings", lambda: NS(full_context_max_tokens=5, top_k=2))
    chunks = [rc(1, 0.2, 10, 40, "a" * 100), rc(2, 0.9, 50, 80, "b" * 100), rc(3, 0.5, 80, 99, "c" * 100)]
    out, client = run(chunks)
    assert out.mode == "retrieval"
    _, user = prompt_of(client)
    assert "b" * 100 in user and "c" * 100 in user and "a" * 100 not in user
    assert user.index("c" * 100) > user.index("b" * 100)  # still video order


def test_low_similarity_no_longer_blocks_the_model():
    """Similarity only ranks context; whether the video has the answer is the model's call."""
    out, client = run([rc(1, 0.03, text="Katrina Kaif is trolled")], reply="She shows everyone is judged [C1].")
    client.invoke.assert_called_once()
    assert out.grounded and [s.chunk_id for s in out.sources] == ["c1"]


def test_model_declares_insufficient_context():
    out, _ = run([rc(1, 0.9)], reply=INSUFFICIENT_MARKER)
    assert out.grounded is False and out.answer == NO_CONTEXT_ANSWER and out.sources == []


def test_video_without_transcript_says_so_without_llm():
    out, client = run([])
    assert out.grounded is False and out.sources == []
    client.invoke.assert_not_called()


# ---------------------------------------------------------------- citations


def test_only_cited_excerpts_become_sources_and_markers_become_real_timestamps():
    chunks = [rc(1, 0.9, 10, 40), rc(2, 0.8, 50, 80), rc(3, 0.7, 80, 99)]
    out, _ = run(chunks, reply="First point [C2]. Second point [C2][C3].")
    assert [s.chunk_id for s in out.sources] == ["c2", "c3"]  # c1 was context but not cited
    assert out.answer == "First point [00:50–01:20]. Second point [00:50–01:20][01:20–01:39]."


@pytest.mark.parametrize("reply,expected_ids,expected_text", [
    ("Fact [C1, C2].", ["c1", "c2"], "Fact [00:10–00:40, 00:50–01:20]."),
    ("Fact 【C2】.", ["c2"], "Fact [00:50–01:20]."),
    ("Fact [C9].", None, "Fact."),  # unknown id dropped, never shown
    ("Fact [C1] and fake [C7].", ["c1"], "Fact [00:10–00:40] and fake."),
    ("Fact [c2].", ["c2"], "Fact [00:50–01:20]."),  # lowercase
    ("Fact [C1-C2].", ["c1", "c2"], "Fact [00:10–00:40, 00:50–01:20]."),  # range
    ("Fact [C1–C2].", ["c1", "c2"], "Fact [00:10–00:40, 00:50–01:20]."),  # en-dash range
    ("Fact [C1 and C2].", ["c1", "c2"], "Fact [00:10–00:40, 00:50–01:20]."),
    ("Fact [C2, c1].", ["c2", "c1"], "Fact [00:50–01:20, 00:10–00:40]."),
    ("Fact [C1-C99].", ["c1"], "Fact [00:10–00:40]."),  # absurd range: only the first id
])
def test_citation_formats_and_unknown_ids(reply, expected_ids, expected_text):
    out, _ = run([rc(1, 0.4, 10, 40), rc(2, 0.9, 50, 80)], reply=reply)
    assert out.answer == expected_text
    if expected_ids is not None:
        assert [s.chunk_id for s in out.sources] == expected_ids


def test_answer_without_usable_citations_falls_back_to_most_similar():
    chunks = [rc(1, 0.1, 10, 40), rc(2, 0.9, 50, 80), rc(3, 0.5, 80, 99)]
    out, _ = run(chunks, reply="An answer with no citation.")
    assert out.grounded and [s.chunk_id for s in out.sources] == ["c2", "c3"]


def test_empty_question_rejected():
    with pytest.raises(AppError) as exc:
        answer_question("v1", "  ", chunk_repo=MagicMock(), model=fake_model(), llm_client=fake_llm())
    assert exc.value.error == "EMPTY_MESSAGE"


# ---------------------------------------------------------------- LLM error mapping


def _groq_error(cls, status=None):
    req = httpx.Request("POST", "https://api.groq.com/x")
    if cls in (groq.APIConnectionError,):
        return cls(request=req)
    if cls is groq.APITimeoutError:
        return cls(request=req)
    return cls("boom secret", response=httpx.Response(status, request=req), body=None)


@pytest.mark.parametrize(
    "exc,code,status",
    [
        (_groq_error(groq.RateLimitError, 429), "LLM_RATE_LIMITED", 429),
        (_groq_error(groq.APITimeoutError), "LLM_UNAVAILABLE", 503),
        (_groq_error(groq.APIConnectionError), "LLM_UNAVAILABLE", 503),
        (_groq_error(groq.AuthenticationError, 401), "LLM_NOT_CONFIGURED", 503),
        (_groq_error(groq.NotFoundError, 404), "LLM_NOT_CONFIGURED", 503),
        (RuntimeError("secret internals"), "LLM_ERROR", 503),
    ],
)
def test_llm_error_mapping(exc, code, status):
    client = MagicMock()
    client.invoke.side_effect = exc
    with pytest.raises(AppError) as e:
        llm.generate("sys", "user", llm=client)
    assert e.value.error == code and e.value.status_code == status
    assert "secret" not in e.value.message


def test_llm_empty_response_is_error():
    with pytest.raises(AppError) as e:
        llm.generate("s", "u", llm=fake_llm("   "))
    assert e.value.error == "LLM_ERROR"


def test_llm_not_configured(monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: NS(groq_api_key="", groq_model="x", groq_temperature=0, groq_timeout_seconds=1))
    with pytest.raises(AppError) as e:
        llm.generate("s", "u")
    assert e.value.error == "LLM_NOT_CONFIGURED"


def test_llm_placeholder_values_count_as_not_configured(monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: NS(
        groq_api_key="your_groq_api_key_here", groq_model="your_groq_model_name_here",
        groq_temperature=0, groq_timeout_seconds=1))
    with pytest.raises(AppError) as e:
        llm.generate("s", "u")
    assert e.value.error == "LLM_NOT_CONFIGURED"


# ---------------------------------------------------------------- startup warm-up


def test_startup_survives_warmup_failure(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main

    monkeypatch.setattr("app.services.embeddings.embed_query", MagicMock(side_effect=RuntimeError("no model")))
    monkeypatch.setattr(main, "get_settings", lambda: NS(warmup_embeddings=True, cors_origins=[]))
    with TestClient(main.app) as client:  # runs lifespan
        assert client.get("/health").status_code == 200


def test_warmup_can_be_disabled(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main

    spy = MagicMock()
    monkeypatch.setattr("app.services.embeddings.embed_query", spy)
    monkeypatch.setattr(main, "get_settings", lambda: NS(warmup_embeddings=False, cors_origins=[]))
    with TestClient(main.app):
        pass
    spy.assert_not_called()


# ---------------------------------------------------------------- output cap / truncation


def test_truncated_response_is_an_error_not_a_partial_answer():
    client = MagicMock()
    client.invoke.return_value = NS(content="half an ans", response_metadata={"finish_reason": "length"})
    with pytest.raises(AppError) as e:
        llm.generate("s", "u", llm=client)
    assert e.value.error == "LLM_ERROR" and "cut off" in e.value.message


def test_normal_finish_reason_is_fine():
    client = MagicMock()
    client.invoke.return_value = NS(content="full answer", response_metadata={"finish_reason": "stop"})
    assert llm.generate("s", "u", llm=client) == "full answer"


def test_llm_is_built_with_generous_token_cap_and_reasoning_effort(monkeypatch):
    captured = {}
    monkeypatch.setattr(llm, "ChatGroq", lambda **kw: captured.update(kw) or "built")
    monkeypatch.setattr(llm, "get_settings", lambda: NS(
        groq_api_key="k", groq_model="m", groq_temperature=0.1, groq_timeout_seconds=60,
        groq_max_tokens=8192, groq_reasoning_effort="low"))
    assert llm._build_llm() == "built"
    assert captured["max_tokens"] == 8192 and captured["reasoning_effort"] == "low"


def test_empty_reasoning_effort_is_not_sent(monkeypatch):
    captured = {}
    monkeypatch.setattr(llm, "ChatGroq", lambda **kw: captured.update(kw) or "built")
    monkeypatch.setattr(llm, "get_settings", lambda: NS(
        groq_api_key="k", groq_model="m", groq_temperature=0.1, groq_timeout_seconds=60,
        groq_max_tokens=100, groq_reasoning_effort=""))
    llm._build_llm()
    assert "reasoning_effort" not in captured
