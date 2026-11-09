"""Group transcript segments into ~chunk_size-character chunks that keep timestamps.

Chunks are built from whole transcript segments so timestamps stay exact. A segment
is only split (on word boundaries, timestamps interpolated by character position)
when it is longer than chunk_size on its own. Overlap is made of whole trailing
segments from the previous chunk, up to chunk_overlap characters.
"""
from app.core.config import get_settings
from app.schemas.chunk import TranscriptChunk
from app.schemas.transcript import Transcript, TranscriptSegment


def _split_long_segment(seg: TranscriptSegment, max_chars: int) -> list[TranscriptSegment]:
    """Split one oversized segment on word boundaries, interpolating timestamps."""
    if len(seg.text) <= max_chars:
        return [seg]

    pieces: list[str] = []
    current = ""
    for word in seg.text.split(" "):
        while len(word) > max_chars:  # a single "word" longer than a chunk: hard split
            if current:
                pieces.append(current)
                current = ""
            pieces.append(word[:max_chars])
            word = word[max_chars:]
        candidate = f"{current} {word}" if current else word
        if len(candidate) > max_chars:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)

    total = sum(len(p) for p in pieces) or 1
    result, offset = [], 0
    for p in pieces:
        start = seg.start + seg.duration * (offset / total)
        offset += len(p)
        end = seg.start + seg.duration * (offset / total)
        result.append(TranscriptSegment(text=p, start=start, duration=end - start))
    return result


def _joined_length(segments: list[TranscriptSegment]) -> int:
    if not segments:
        return 0
    return sum(len(s.text) for s in segments) + len(segments) - 1  # single spaces


def _make_chunk(index: int, segments: list[TranscriptSegment]) -> TranscriptChunk:
    return TranscriptChunk(
        chunk_index=index,
        content=" ".join(s.text for s in segments),
        start_time=segments[0].start,
        end_time=max(s.end for s in segments),
    )


def chunk_segments(
    segments: list[TranscriptSegment],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[TranscriptChunk]:
    settings = get_settings()
    chunk_size = settings.chunk_size if chunk_size is None else chunk_size
    chunk_overlap = settings.chunk_overlap if chunk_overlap is None else chunk_overlap
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size")

    units: list[TranscriptSegment] = []
    for seg in segments:
        if seg.text.strip():
            units.extend(_split_long_segment(seg, chunk_size))

    chunks: list[TranscriptChunk] = []
    current: list[TranscriptSegment] = []
    new_in_current = 0  # units in `current` that are not carried-over overlap

    for unit in units:
        if current and _joined_length(current + [unit]) > chunk_size:
            chunks.append(_make_chunk(len(chunks), current))
            # Carry over trailing whole segments (<= chunk_overlap chars) as overlap.
            overlap: list[TranscriptSegment] = []
            for prev in reversed(current):
                if _joined_length([prev] + overlap) > chunk_overlap:
                    break
                overlap.insert(0, prev)
            # Always leave room for the new unit so we make progress.
            while overlap and _joined_length(overlap + [unit]) > chunk_size:
                overlap.pop(0)
            current, new_in_current = overlap, 0
        current.append(unit)
        new_in_current += 1

    if current and new_in_current:
        chunks.append(_make_chunk(len(chunks), current))
    return chunks


def chunk_transcript(transcript: Transcript, **kwargs) -> list[TranscriptChunk]:
    return chunk_segments(transcript.segments, **kwargs)
