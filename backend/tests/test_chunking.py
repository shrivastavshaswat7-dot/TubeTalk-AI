import pytest

from app.schemas.transcript import Transcript, TranscriptSegment
from app.services.chunking import chunk_segments, chunk_transcript


def make_segments(n=200, text_len=40, step=3.0):
    return [
        TranscriptSegment(text=f"{i:04d} " + "x" * (text_len - 5), start=i * step, duration=step - 0.5)
        for i in range(n)
    ]


def test_empty_transcript():
    assert chunk_segments([]) == []
    assert chunk_segments([TranscriptSegment("  ", 0, 1)]) == []
    assert chunk_transcript(Transcript("vid", "en", False, [])) == []


def test_chunk_size_respected_and_indexes_sequential():
    chunks = chunk_segments(make_segments(), 800, 150)
    assert len(chunks) > 1
    assert all(len(c.content) <= 800 for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # chunks should be reasonably full, not tiny (except possibly the last one)
    assert all(len(c.content) > 600 for c in chunks[:-1])


def test_chronological_order_and_timestamps_exact():
    segs = make_segments()
    chunks = chunk_segments(segs, 800, 150)
    starts = [c.start_time for c in chunks]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)
    assert chunks[0].start_time == segs[0].start
    assert chunks[-1].end_time == segs[-1].end
    for c in chunks:
        assert c.start_time < c.end_time
        # first segment's text (its 4-digit id) must match the chunk start time
        first_id = int(c.content[:4])
        assert c.start_time == segs[first_id].start
        last_id = int(c.content.split(" ")[-2])
        assert c.end_time == segs[last_id].end


def test_overlap_correct():
    segs = make_segments()
    chunks = chunk_segments(segs, 800, 150)
    for prev, nxt in zip(chunks, chunks[1:]):
        prev_ids = [int(w) for w in prev.content.split(" ") if len(w) == 4 and w.isdigit()]
        next_ids = [int(w) for w in nxt.content.split(" ") if len(w) == 4 and w.isdigit()]
        shared = set(prev_ids) & set(next_ids)
        assert shared, "consecutive chunks must overlap"
        overlap_text = " ".join(
            s.text for s in segs if s.start >= nxt.start_time and s.end <= prev.end_time
        )
        assert 0 < len(overlap_text) <= 150
        assert nxt.start_time < prev.end_time  # overlap in time too
        assert nxt.start_time > prev.start_time  # but always moves forward


def test_zero_overlap_has_no_shared_segments():
    segs = make_segments()
    chunks = chunk_segments(segs, 800, 0)
    assert len(chunks) > 1
    for prev, nxt in zip(chunks, chunks[1:]):
        last_prev = int(prev.content.split(" ")[-2])
        assert int(nxt.content[:4]) == last_prev + 1  # next chunk starts right after


def test_no_lost_content():
    segs = make_segments()
    chunks = chunk_segments(segs, 800, 150)
    seen = set()
    for c in chunks:
        seen.update(w for w in c.content.split(" ") if len(w) == 4 and w.isdigit())
    assert seen == {f"{i:04d}" for i in range(len(segs))}
    all_text = " ".join(c.content for c in chunks)
    for s in segs:
        assert s.text in all_text


def test_single_segment_larger_than_target_is_split_safely():
    words = " ".join(f"word{i}" for i in range(600))  # ~4000 chars
    seg = TranscriptSegment(words, start=100.0, duration=60.0)
    chunks = chunk_segments([seg], 800, 150)
    assert len(chunks) > 1
    assert all(len(c.content) <= 800 for c in chunks)
    assert chunks[0].start_time == 100.0
    assert chunks[-1].end_time == pytest.approx(160.0)
    starts = [c.start_time for c in chunks]
    assert starts == sorted(starts)
    # every word is preserved in order
    rebuilt = [w for c in chunks for w in c.content.split(" ")]
    assert [w for w in words.split(" ") if w in set(rebuilt)] == words.split(" ")
    assert set(rebuilt) == set(words.split(" "))


def test_single_unbroken_token_longer_than_chunk():
    seg = TranscriptSegment("a" * 2000, 0.0, 10.0)
    chunks = chunk_segments([seg], 800, 150)
    assert all(len(c.content) <= 800 for c in chunks)
    assert sum(len(c.content) for c in chunks) >= 2000


def test_short_transcript_is_one_chunk():
    segs = [TranscriptSegment("hello", 1.0, 1.0), TranscriptSegment("world", 2.0, 1.5)]
    chunks = chunk_segments(segs, 800, 150)
    assert len(chunks) == 1
    assert chunks[0].content == "hello world"
    assert (chunks[0].start_time, chunks[0].end_time) == (1.0, 3.5)


def test_defaults_come_from_settings():
    chunks = chunk_segments(make_segments())
    assert all(len(c.content) <= 800 for c in chunks)


@pytest.mark.parametrize("size,overlap", [(0, 0), (100, 100), (100, -1), (100, 150)])
def test_invalid_parameters(size, overlap):
    with pytest.raises(ValueError):
        chunk_segments(make_segments(5), size, overlap)
