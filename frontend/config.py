"""Frontend settings: API URL comes from env var or Streamlit secrets, never hardcoded."""
import os

import streamlit as st


def get_api_base_url() -> str:
    url = os.getenv("API_BASE_URL")
    if not url:
        try:
            url = st.secrets.get("API_BASE_URL")
        except Exception:  # no secrets file configured
            url = None
    return (url or "http://localhost:8000").rstrip("/")
