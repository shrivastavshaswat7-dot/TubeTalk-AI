"""Application settings loaded from environment variables (and backend/.env locally)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "development"

    # External services (empty until configured; validated where they are used)
    groq_api_key: str = ""
    groq_model: str = ""
    supabase_url: str = ""
    supabase_key: str = ""

    allowed_origins: str = "http://localhost:8501"

    # RAG parameters (experimental starting values, see docs/06_RAG_Pipeline.md)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_size: int = 800
    chunk_overlap: int = 150
    top_k: int = 5
    # Cosine similarity a topic starter question must reach to be suggested. Answers no longer use
    # it as a gate: similarity ranks context, and the model decides whether the video has the answer.
    min_similarity: float = 0.25
    # Transcripts up to this size (estimated tokens) are passed to the model whole; longer ones use
    # the TOP_K most similar chunks.
    full_context_max_tokens: int = 6000

    # LLM behaviour
    groq_temperature: float = 0.1
    groq_timeout_seconds: float = 60.0
    # Reasoning models (e.g. gpt-oss) spend completion tokens on hidden reasoning, so the cap must be
    # generous or answers come back empty/truncated. Empty reasoning effort = provider default.
    groq_max_tokens: int = 8192
    groq_reasoning_effort: str = "low"

    # Load the embedding model in the background at startup (avoids a slow first request)
    warmup_embeddings: bool = True

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
