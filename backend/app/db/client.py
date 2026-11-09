"""Supabase client factory (backend only; uses the service-role key)."""
from functools import lru_cache

from supabase import Client, create_client

from app.core.config import get_settings
from app.core.errors import AppError


@lru_cache
def get_client() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise AppError(
            "DATABASE_NOT_CONFIGURED",
            "The database is not configured. Set SUPABASE_URL and SUPABASE_KEY.",
            503,
        )
    return create_client(settings.supabase_url, settings.supabase_key)
