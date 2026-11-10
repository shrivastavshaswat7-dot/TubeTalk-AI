"""Frontend settings: API URL comes from env var or Streamlit secrets, never hardcoded."""
import os

import streamlit as st

MISSING_API_URL_MESSAGE = (
    "TubeTalk AI isn't configured yet: the backend address (API_BASE_URL) is missing. "
    "Set API_BASE_URL as an environment variable or in the Streamlit secrets, "
    "for example http://localhost:8000 when running the backend locally."
)


def get_api_base_url() -> str:
    """The backend address, or "" if it isn't configured (app.py then shows a configuration error
    instead of quietly calling localhost, which would never work in a deployment)."""
    url = os.getenv("API_BASE_URL")
    if not url or not url.strip():
        try:
            url = st.secrets.get("API_BASE_URL")
        except Exception:  # no secrets file configured
            url = None
    return (url or "").strip().rstrip("/")
