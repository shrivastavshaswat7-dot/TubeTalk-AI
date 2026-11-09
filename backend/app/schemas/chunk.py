from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptChunk:
    chunk_index: int
    content: str
    start_time: float  # seconds
    end_time: float  # seconds


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    chunk_index: int
    content: str
    start_time: float | None
    end_time: float | None
    similarity: float  # cosine similarity, higher is closer
