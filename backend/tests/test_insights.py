import json
from unittest.mock import MagicMock

import pytest

from app.core.errors import AppError
from app.prompts.insights import CONDENSE_SYSTEM_PROMPT, FINAL_SYSTEM_PROMPT, MAP_SYSTEM_PROMPT
from app.services import insights as ins
from app.services.insights import generate_insights, get_or_generate, parse_insights, parse_timestamp
from tests.fakes import FakeChunkRepo, FakeInsightsRepo, FakeVideoRepo, new_id

FINAL_JSON = {
    "summary": "A summary of the video.",
    "key_takeaways": ["Point one", "Point two", "Point three"],
    "topics": [{"name": "Intro", "timestamp": "00:00"}, {"name": "Main idea", "timestamp": "01:30"}],
}


def mk_chunks(n, size=800, step=60.0):
    return [
        {
            "chunk_index": i,
            "content": (f"chunk{i} " * 200)[:size],
            "start_time": i * step,
            "end_time": i * step + step - 5,
        }
        for i in range(n)
    ]


class ScriptedLLM:
    """Replaces llm.generate: answers by which prompt it receives and records every call."""

    def __init__(self, map_len=300, final=None, errors=None):
        self.calls, self.map_len, self.final, self.errors = [], map_len, final, list(errors or [])

    def __call__(self, system, user, llm=None):
        self.calls.append((system, user))
        if self.errors:
            err = self.errors.pop(0)
            if err:
                raise err
        if system == MAP_SYSTEM_PROMPT or system == CONDENSE_SYSTEM_PROMPT:
            return "- [00:00] note " + "n" * self.map_len
        assert system == FINAL_SYSTEM_PROMPT
        f = self.final if self.final is not None else json.dumps(FINAL_JSON)
        return f(user) if callable(f) else f

    def count(self, prompt):
        return sum(1 for s, _ in self.calls if s == prompt)


@pytest.fixture
def scripted(monkeypatch):
    def install(**kw):
        s = ScriptedLLM(**kw)
        monkeypatch.setattr("app.services.llm.generate", s)
        return s

    return install


# ---------------------------------------------------------------- parsing


@pytest.mark.parametrize(
    "value,expected",
    [
        ("00:00", 0.0),
        ("04:35", 275.0),
        ("[01:02]", 62.0),
        ("1:02:05", None),  # beyond a 600s video
        ("99:99", None),
        ("abc", None),
        (None, None),
        (275, None),
        ("10:00", 600.0),
        ("40:00", None),
    ],
)
def test_parse_timestamp(value, expected):
    assert parse_timestamp(value, max_seconds=600) == expected


def test_parse_timestamp_hours():
    assert parse_timestamp("1:02:05", max_seconds=4000) == 3725.0


def test_parse_insights_accepts_fenced_json_and_caps_lists():
    payload = {
        "summary": " S ",
        "key_takeaways": [f"t{i}" for i in range(30)] + ["", 5],
        "topics": [{"name": f"topic{i}", "timestamp": "00:10"} for i in range(30)],
    }
    out = parse_insights("```json\n" + json.dumps(payload) + "\n```", 100)
    assert out.summary == "S"
    assert len(out.key_takeaways) == ins.MAX_TAKEAWAYS and len(out.topics) == ins.MAX_TOPICS
    assert out.topics[0] == {"name": "topic0", "start_time": 10.0}


def test_parse_insights_nulls_invalid_timestamps_but_keeps_topic():
    payload = dict(FINAL_JSON, topics=[{"name": "X", "timestamp": "59:59"}, {"name": "Y"}])
    out = parse_insights(json.dumps(payload), max_seconds=100)
    assert [t["start_time"] for t in out.topics] == [None, None]


@pytest.mark.parametrize(
    "bad",
    [
        "no json here",
        "{not json}",
        json.dumps({"summary": "", "key_takeaways": ["a"], "topics": [{"name": "t"}]}),
        json.dumps({"summary": "s", "key_takeaways": [], "topics": [{"name": "t"}]}),
        json.dumps({"summary": "s", "key_takeaways": ["a"], "topics": []}),
        json.dumps({"summary": "s", "key_takeaways": "a", "topics": [{"name": "t"}]}),
    ],
)
def test_parse_insights_rejects_bad_output(bad):
    with pytest.raises((ValueError, json.JSONDecodeError)):
        parse_insights(bad, 100)


# ---------------------------------------------------------------- generation


def test_short_transcript_single_pass_uses_full_transcript_with_timestamps(scripted):
    s = scripted()
    chunks = mk_chunks(5)  # 4k chars
    out = generate_insights(chunks)
    assert out.summary == "A summary of the video." and out.topics[1]["start_time"] == 90.0
    assert len(s.calls) == 1 and s.count(FINAL_SYSTEM_PROMPT) == 1
    prompt = s.calls[0][1]
    assert all(c["content"] in prompt for c in chunks)  # EVERY chunk, not just the top 5 matches
    assert "[00:00]" in prompt and "[04:00]" in prompt


def test_long_transcript_uses_map_reduce_and_never_sends_oversized_prompts(scripted):
    s = scripted(map_len=300)
    chunks = mk_chunks(100)  # 80k chars, far above the single-pass limit
    out = generate_insights(chunks)
    assert out.key_takeaways
    sections = len(ins.split_sections(chunks))
    assert sections >= 8 and s.count(MAP_SYSTEM_PROMPT) == sections
    assert s.count(FINAL_SYSTEM_PROMPT) == 1
    # every part of the transcript reached some map call
    map_inputs = " ".join(u for sys_, u in s.calls if sys_ == MAP_SYSTEM_PROMPT)
    assert all(f"chunk{i} " in map_inputs for i in (0, 50, 99))
    # no prompt exceeds the context budget: this is what protects against context overflow
    assert max(len(u) for _, u in s.calls) <= ins.SECTION_CHARS + 2000
    assert len(s.calls[-1][1]) <= ins.REDUCE_MAX_CHARS


def test_long_transcript_with_big_notes_runs_reduce_rounds(scripted):
    s = scripted(map_len=2500)  # 8+ sections x 2.5k chars > REDUCE_MAX_CHARS
    generate_insights(mk_chunks(100))
    assert s.count(CONDENSE_SYSTEM_PROMPT) >= 1
    assert len(s.calls[-1][1]) <= ins.REDUCE_MAX_CHARS


def test_notes_that_never_shrink_fail_safely(scripted):
    s = scripted(map_len=9000)  # condense output as large as its input: cannot converge
    with pytest.raises(AppError) as e:
        generate_insights(mk_chunks(100))
    assert e.value.error == "INSIGHTS_FAILED"
    assert s.count(CONDENSE_SYSTEM_PROMPT) < 100  # bounded work


def test_invalid_json_retried_once_then_succeeds(scripted):
    replies = iter(["sorry, here you go: not json", json.dumps(FINAL_JSON)])
    s = scripted(final=lambda user: next(replies))
    assert generate_insights(mk_chunks(3)).summary
    assert s.count(FINAL_SYSTEM_PROMPT) == 2 and "valid JSON" in s.calls[-1][1]


def test_invalid_json_twice_fails(scripted):
    scripted(final="never json")
    with pytest.raises(AppError) as e:
        generate_insights(mk_chunks(3))
    assert e.value.error == "INSIGHTS_FAILED"


def test_rate_limit_waits_and_retries(scripted):
    rl = AppError("LLM_RATE_LIMITED", "busy", 429)
    s = scripted(errors=[rl, rl])
    sleeps = []
    out = generate_insights(mk_chunks(3), sleep=sleeps.append)
    assert out.summary and sleeps == [5, 15] and len(s.calls) == 3


def test_persistent_rate_limit_gives_up(scripted):
    rl = AppError("LLM_RATE_LIMITED", "busy", 429)
    scripted(errors=[rl] * 10)
    sleeps = []
    with pytest.raises(AppError) as e:
        generate_insights(mk_chunks(3), sleep=sleeps.append)
    assert e.value.error == "LLM_RATE_LIMITED" and sleeps == [5, 15, 30]


def test_other_llm_errors_are_not_retried(scripted):
    s = scripted(errors=[AppError("LLM_NOT_CONFIGURED", "bad key", 503)])
    with pytest.raises(AppError) as e:
        generate_insights(mk_chunks(3), sleep=lambda _: pytest.fail("must not sleep"))
    assert e.value.error == "LLM_NOT_CONFIGURED" and len(s.calls) == 1


def test_empty_transcript():
    with pytest.raises(AppError) as e:
        generate_insights([])
    assert e.value.error == "TRANSCRIPT_UNAVAILABLE"


# ---------------------------------------------------------------- caching service


@pytest.fixture
def repos():
    videos, insights, chunks = FakeVideoRepo(), FakeInsightsRepo(), FakeChunkRepo()
    vid = new_id()
    videos.rows[vid] = {
        "id": vid,
        "youtube_video_id": "abc",
        "youtube_url": "https://www.youtube.com/watch?v=abc",
        "processing_status": "completed",
    }
    chunks.by_video[vid] = [dict(c, id=new_id()) for c in mk_chunks(5)]
    return videos, insights, chunks, vid


def run(repos, **kw):
    videos, insights, chunks, vid = repos
    return get_or_generate(vid, videos, insights, chunks, sleep=lambda _: None, **kw)


def test_first_call_generates_and_stores_then_second_is_cached(repos, scripted):
    s = scripted()
    row, cached = run(repos)
    assert cached is False and row["status"] == "completed" and row["summary"] and row["generated_at"]
    assert row["topics"][1] == {"name": "Main idea", "start_time": 90.0}
    n = len(s.calls)
    row2, cached2 = run(repos)
    assert cached2 is True and row2["summary"] == row["summary"]
    assert len(s.calls) == n  # no LLM call on a cached request


def test_force_regenerates(repos, scripted):
    s = scripted()
    run(repos)
    n = len(s.calls)
    _, cached = run(repos, force=True)
    assert cached is False and len(s.calls) == n + 1


def test_first_failure_is_stored_as_failed_and_retried_next_time(repos, scripted):
    scripted(errors=[AppError("LLM_ERROR", "down", 503)])
    with pytest.raises(AppError):
        run(repos)
    stored = repos[1].rows[repos[3]]
    assert stored["status"] == "failed" and stored["error_message"] and not stored["summary"]
    row, cached = run(repos)  # failed rows are retried, never served
    assert cached is False and row["status"] == "completed" and row["error_message"] is None


def test_failed_regeneration_keeps_previous_insights(repos, scripted):
    scripted()
    first, _ = run(repos)
    scripted(errors=[AppError("LLM_ERROR", "down", 503)])
    with pytest.raises(AppError):
        run(repos, force=True)
    stored = repos[1].rows[repos[3]]
    assert stored["status"] == "completed" and stored["summary"] == first["summary"]
    assert stored["error_message"] == "down"
    scripted()
    row, cached = run(repos)  # a plain GET still serves the preserved insights
    assert cached is True and row["summary"] == first["summary"]


def test_unexpected_exception_becomes_insights_failed(repos, monkeypatch):
    monkeypatch.setattr("app.services.llm.generate", MagicMock(side_effect=RuntimeError("secret internals")))
    with pytest.raises(AppError) as e:
        run(repos)
    assert e.value.error == "INSIGHTS_FAILED" and "secret" not in e.value.message
    assert repos[1].rows[repos[3]]["status"] == "failed"


def test_concurrent_generation_rejected_but_stale_retried(repos, scripted):
    scripted()
    videos, insights, chunks, vid = repos
    insights.mark_generating(vid)
    with pytest.raises(AppError) as e:
        run(repos)
    assert e.value.error == "INSIGHTS_GENERATING" and e.value.status_code == 409
    insights.rows[vid]["updated_at"] = "2020-01-01T00:00:00+00:00"
    assert run(repos)[1] is False


def test_video_must_exist_and_be_completed(repos, scripted):
    scripted()
    videos, insights, chunks, vid = repos
    with pytest.raises(AppError) as e:
        get_or_generate("00000000-0000-4000-8000-999999999999", videos, insights, chunks)
    assert e.value.error == "VIDEO_NOT_FOUND"
    videos.rows[vid]["processing_status"] = "failed"
    with pytest.raises(AppError) as e:
        run(repos)
    assert e.value.error == "VIDEO_NOT_READY"
