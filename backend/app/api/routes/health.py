import os
import re
from pathlib import Path

from fastapi import APIRouter

from app.core.config import Settings

router = APIRouter(tags=["health"])

REQUIRED_ENV = ("GROQ_API_KEY", "GROQ_MODEL", "SUPABASE_URL", "SUPABASE_KEY")
SECRET_FILES_DIR = Path("/etc/secrets")  # where Render mounts "Secret Files"
_INVISIBLE = re.compile(r"[\s​-‍⁠﻿]")


@router.get("/")
def root():
    return {"message": "TubeTalk AI Backend is running"}


@router.get("/health")
def health():
    return {"status": "healthy", "application": "TubeTalk AI"}


@router.get("/health/config")
def config_check():
    """Deployment diagnostic: true/false only per required variable. Never returns values,
    partial values or lengths."""
    settings = Settings()  # fresh read of the current environment (not the cached instance)
    report = {}
    for name in REQUIRED_ENV:
        near_miss = any(
            key != name and _INVISIBLE.sub("", key).upper() == name for key in os.environ
        )
        report[name] = {
            "present": name in os.environ,
            "non_empty": bool(os.environ.get(name, "").strip()),
            "loaded_by_settings": bool(getattr(settings, name.lower())),
            "near_miss_name": near_miss,  # e.g. a hidden space or invisible character in the name
            "secret_file": (SECRET_FILES_DIR / name).is_file(),
        }
    return {"variables": report}
