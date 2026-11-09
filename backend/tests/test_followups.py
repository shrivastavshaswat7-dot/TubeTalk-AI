"""Conversational follow-ups. History helps resolve references (never as evidence), retrieval
stays anchored when the rewrite fails, and unresolvable references get a clarifying question."""
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.errors import AppError
from app.main import app
from app.prompts.rag import CLARIFY_MARKER, DEFAULT_CLARIFICATION, INSUFFICIENT_MARKER, build_user_message, format_history
from app.schemas.chunk import RetrievedChunk
from app.services.chat import build_retrieval_query
from app.services.embeddings import EMBEDDING_DIMENSION
from app.services.rag import answer_question
from tests.fakes import FakeChunkRepo, FakeInsightsRepo, FakeMessageRepo, FakeSessionRepo, FakeVideoRepo, new_id


def u(text):
    return {"role": "user", "content": text}


def a(text):
    return {"role": "assistant", "content": text}


REVERSAL = [u("What is the reversal curse?"), a("It means knowledge is one-directional [12:12–12:54].")]
KATRINA = [u("Why does the speaker mention Katrina Kaif?"), a("To show everyone is judged [00:00–00:49].")]
TOOLS = [u("What tools does the speaker recommend?"), a("ChatGPT or Gemini [00:39–01:31].")]


# ── retrieval query ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("message,standalone,history,expected", [
    # rewrite failed (returned unchanged): anchor on the previous user question
    ("Can you give the example he uses?", "Can you give the example he uses?", REVERSAL,
     "What is the reversal curse? Can you give the example he uses?"),
    # rewrite still unresolved ("her"): never trusted alone
    ("Why does he mention her?", "Why does the speaker mention her?", KATRINA,
     "Why does the speaker mention Katrina Kaif? Why does the speaker mention her?"),
    # rewrite resolved the reference: used as-is
    ("How do I use them?", "How do I use ChatGPT and Gemini?", TOOLS, "How do I use ChatGPT and Gemini?"),
    # not a follow-up: the question itself
    ("How long should each session be?", "How long should each session be?", TOOLS, "How long should each session be?"),
    # no history: nothing to anchor on
    ("Why does he mention her?", "Why does he mention her?", [], "Why does he mention her?"),
])
def test_build_retrieval_query(message, standalone, history, expected):
    assert build_retrieval_query(message, standalone, history) == expected


def test_retrieval_query_uses_latest_user_question():
    history = REVERSAL + [u("And what about the Tom Cruise part?"), a("...")]
    assert build_retrieval_query("Why is it weird?", "Why is it weird?", history).startswith(
        "And what about the Tom Cruise part?")


# ── prompt and answer handling ────────────────────────────────────────────────


def rc(i, sim, start, end, text):
    return RetrievedChunk(f"c{i}", i, text, start, end, sim)


def repo_returning(chunks):
    rows = [{"id": c.chunk_id, "chunk_index": c.chunk_index, "content": c.content,
             "start_time": c.start_time, "end_time": c.end_time, "similarity": c.similarity} for c in chunks]
    repo = MagicMock()
    repo.list_for_video.return_value = [{k: v for k, v in r.items() if k != "similarity"} for r in rows]
    repo.match.side_effect = lambda video_id, emb, k: sorted(rows, key=lambda r: -r["similarity"])[:k]
    return repo


def recording_model():
    m = MagicMock()
    m.encoded = []
    m.encode.side_effect = lambda texts, **kw: m.encoded.extend(texts) or [[0.1] * EMBEDDING_DIMENSION for _ in texts]
    return m


def llm_replying(text):
    m = MagicMock()
    m.invoke.return_value = NS(content=text)
    return m


CHUNKS = [rc(0, 0.5, 0, 40, "Tom Cruise's mother is Mary Lee Pfeiffer, but not the reverse.")]


def test_history_is_in_the_prompt_but_framed_as_not_evidence():
    client = llm_replying("Tom Cruise's mother example [C1].")
    answer_question("v1", "Can you give the example he uses?", chunk_repo=repo_returning(CHUNKS), model=recording_model(),
                    llm_client=client, history=REVERSAL, interpreted="Can you give the example used for the reversal curse?")
    system, user = (m.content for m in client.invoke.call_args.args[0])
    assert "not evidence" in user and "User: What is the reversal curse?" in user
    assert "Current question: Can you give the example he uses?" in user  # the user's own words
    assert "(Interpreted as: Can you give the example used for the reversal curse?)" in user
    assert "never repeat a fact from an earlier answer unless the excerpts support it" in system


def test_history_is_limited_to_recent_turns_and_truncated():
    history = [u(f"q{i}") if i % 2 == 0 else a(f"a{i}") for i in range(10)] + [a("x" * 2000)]
    text = format_history(history)
    assert "q0" not in text and "a9" in text  # only the last 3 exchanges
    assert "x" * 600 + "..." in text and "x" * 601 not in text


def test_no_interpreted_line_when_rewrite_is_identical():
    msg = build_user_message(CHUNKS, "What is X?", history=None, interpreted="What is X?")
    assert "Interpreted as" not in msg and "(none)" in msg


def test_retrieval_uses_the_retrieval_query_not_the_bare_follow_up():
    model = recording_model()
    answer_question("v1", "Can you give the example he uses?", chunk_repo=repo_returning(CHUNKS), model=model,
                    llm_client=llm_replying("Example [C1]."), retrieval_query="What is the reversal curse? Can you give the example he uses?")
    assert model.encoded == ["What is the reversal curse? Can you give the example he uses?"]


@pytest.mark.parametrize("reply,expected", [
    (f"{CLARIFY_MARKER}: Which example do you mean?", "Which example do you mean?"),
    (CLARIFY_MARKER, DEFAULT_CLARIFICATION),
    (f"{CLARIFY_MARKER}: Who is 'she'? {INSUFFICIENT_MARKER}", f"Who is 'she'? {INSUFFICIENT_MARKER}"),  # clarification wins
])
def test_clarification_reply(reply, expected):
    out = answer_question("v1", "What did he say about that?", chunk_repo=repo_returning(CHUNKS),
                          model=recording_model(), llm_client=llm_replying(reply))
    assert out.kind == "clarification" and out.grounded is False and out.sources == []
    assert out.answer == expected


@pytest.mark.parametrize("question", ["What is the capital of France?", "How do I prepare for IELTS?"])
def test_clear_question_is_never_turned_into_a_clarification(question):
    """Regression (live suite): the model asked "Which topic are you asking about?" for a clear,
    absent question. Without a reference word there is nothing to clarify: it is a refusal."""
    out = answer_question("v1", question, chunk_repo=repo_returning(CHUNKS), model=recording_model(),
                          llm_client=llm_replying(f"{CLARIFY_MARKER}: Which topic are you asking about?"))
    assert out.kind == "refusal" and out.grounded is False and "couldn't find" in out.answer


def test_follow_up_without_evidence_is_refused():
    out = answer_question("v1", "How much do they cost?", chunk_repo=repo_returning(CHUNKS), model=recording_model(),
                          llm_client=llm_replying(INSUFFICIENT_MARKER), history=TOOLS)
    assert out.kind == "refusal" and out.grounded is False and out.sources == []


# ── through the chat API ──────────────────────────────────────────────────────

URL = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.fixture
def env(monkeypatch):
    r = NS(videos=FakeVideoRepo(), sessions=FakeSessionRepo(), messages=FakeMessageRepo(),
           chunks=FakeChunkRepo(), insights=FakeInsightsRepo(), searches=[], answer_prompts=[],
           rewrite=lambda history_text, question: question, answer=lambda prompt: "Answer [C1].")
    app.dependency_overrides[deps.get_video_repo] = lambda: r.videos
    app.dependency_overrides[deps.get_session_repo] = lambda: r.sessions
    app.dependency_overrides[deps.get_message_repo] = lambda: r.messages
    app.dependency_overrides[deps.get_chunk_repo] = lambda: r.chunks
    app.dependency_overrides[deps.get_insights_repo] = lambda: r.insights
    r.vid = new_id()
    r.videos.rows[r.vid] = {"id": r.vid, "youtube_video_id": "abcdefghijk", "youtube_url": URL, "processing_status": "completed"}
    r.chunks.by_video[r.vid] = [{"id": "c0", "chunk_index": 0, "content": "Tom Cruise's mother example", "start_time": 0.0, "end_time": 40.0}]
    r.sid = r.sessions.create(r.vid)["id"]

    def fake_generate(system, user, llm=None):
        if "standalone question" in system:  # follow-up rewrite
            question = user.split("Latest message:")[1].split("\n")[0].strip()
            return r.rewrite(user, question)
        r.answer_prompts.append(user)
        return r.answer(user)

    monkeypatch.setattr("app.services.llm.generate", fake_generate)
    monkeypatch.setattr("app.services.retrieval.embed_query", lambda text, model=None: r.searches.append(text) or [0.0] * 384)
    yield r
    app.dependency_overrides.clear()


client = TestClient(app)


def ask(env, text, sid=None):
    return client.post("/api/chat", json={"video_id": env.vid, "session_id": sid or env.sid, "message": text}).json()


def test_example_he_uses_when_rewrite_fails(env):
    ask(env, "What is the reversal curse?")
    body = ask(env, "Can you give the example he uses?")  # rewrite returns it unchanged
    assert env.searches[-1] == "What is the reversal curse? Can you give the example he uses?"
    prompt = env.answer_prompts[-1]
    assert "User: What is the reversal curse?" in prompt and "Current question: Can you give the example he uses?" in prompt
    assert body["answer_type"] == "retrieval" and body["grounded"] is True


def test_why_does_he_mention_her(env):
    ask(env, "Why does the speaker mention Katrina Kaif?")
    env.rewrite = lambda h, q: "Why does the speaker mention her?"  # partially resolved
    ask(env, "Why does he mention her?")
    assert env.searches[-1] == "Why does the speaker mention Katrina Kaif? Why does the speaker mention her?"
    assert "User: Why does the speaker mention Katrina Kaif?" in env.answer_prompts[-1]


def test_how_do_i_use_them_with_a_good_rewrite(env):
    ask(env, "What tools does the speaker recommend?")
    env.rewrite = lambda h, q: "How do I use ChatGPT and Gemini?"
    body = ask(env, "How do I use them?")
    assert env.searches[-1] == "How do I use ChatGPT and Gemini?"
    assert body["standalone_question"] == "How do I use ChatGPT and Gemini?"
    assert "Current question: How do I use them?" in env.answer_prompts[-1]  # original words kept


def test_rewrite_error_falls_back_to_anchored_search(env):
    ask(env, "What is the reversal curse?")

    def broken(h, q):
        raise AppError("LLM_ERROR", "down", 503)

    env.rewrite = broken
    body = ask(env, "Can you give the example he uses?")
    assert env.searches[-1] == "What is the reversal curse? Can you give the example he uses?"
    assert body["grounded"] is True


def test_ambiguous_reference_asks_for_clarification_and_survives_reload(env):
    env.answer = lambda p: f"{CLARIFY_MARKER}: Which part of the video do you mean by 'that'?"
    body = ask(env, "What did he say about that?")
    assert body["answer_type"] == "clarification" and body["grounded"] is False
    assert body["answer"] == "Which part of the video do you mean by 'that'?"
    assert [s["kind"] for s in body["sources"]] == ["clarification"]
    history = client.get(f"/api/sessions/{env.sid}/messages", params={"video_id": env.vid}).json()["messages"]
    assert history[-1]["sources"][0]["kind"] == "clarification"  # still a clarifying question after reload


def test_follow_up_whose_answer_is_absent_is_refused(env):
    ask(env, "What tools does the speaker recommend?")
    env.answer = lambda p: INSUFFICIENT_MARKER
    body = ask(env, "How much do they cost?")
    assert body["grounded"] is False and body["sources"] == [] and "couldn't find" in body["answer"]


def test_history_never_crosses_sessions(env):
    ask(env, "SESSION-ONE SECRET question about Tom Cruise")
    other = env.sessions.create(env.vid)["id"]
    ask(env, "Can you give the example he uses?", sid=other)
    prompt = env.answer_prompts[-1]
    assert "SESSION-ONE" not in prompt and "(none)" in prompt
    assert env.searches[-1] == "Can you give the example he uses?"  # no other session to anchor on


def test_one_answer_call_per_turn(env):
    ask(env, "What is the reversal curse?")
    ask(env, "Can you give the example he uses?")
    assert len(env.answer_prompts) == 2  # no extra LLM call was added for follow-ups
