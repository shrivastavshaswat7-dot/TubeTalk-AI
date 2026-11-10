"""Frontend settings: env var or Streamlit secrets, never hardcoded.

None of these are secret: the Supabase publishable (anon) key is meant to be public; the
database itself is protected by the backend and by row-level security.
"""
import os

import streamlit as st

MISSING_API_URL_MESSAGE = (
    "TubeTalk AI isn't configured yet: the backend address (API_BASE_URL) is missing. "
    "Set API_BASE_URL as an environment variable or in the Streamlit secrets, "
    "for example http://localhost:8000 when running the backend locally."
)

# Google sign-in through Supabase Auth.
AUTH_SETTINGS = ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "APP_URL")
MISSING_AUTH_MESSAGE = (
    "TubeTalk AI isn't configured yet: sign-in needs {names}. Set them as environment variables or "
    "in the Streamlit secrets (APP_URL is this app's own address, e.g. http://localhost:8501)."
)


def get_setting(name: str) -> str:
    """A setting from the environment or the Streamlit secrets, or "" if it isn't set."""
    value = os.getenv(name)
    if not value or not value.strip():
        try:
            value = st.secrets.get(name)
        except Exception:  # no secrets file configured
            value = None
    return (value or "").strip()


def get_api_base_url() -> str:
    """The backend address, or "" if it isn't configured (app.py then shows a configuration error
    instead of quietly calling localhost, which would never work in a deployment)."""
    return get_setting("API_BASE_URL").rstrip("/")


def missing_auth_settings() -> list[str]:
    return [name for name in AUTH_SETTINGS if not get_setting(name)]
