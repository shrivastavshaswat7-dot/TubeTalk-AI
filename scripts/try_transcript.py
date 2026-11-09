"""Manual check against real YouTube (not part of the test suite).

Usage (from repo root, venv active):  python scripts/try_transcript.py <youtube_url>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.errors import AppError  # noqa: E402
from app.services.transcript import fetch_transcript  # noqa: E402
from app.services.youtube import extract_video_id, fetch_metadata  # noqa: E402

try:
    vid = extract_video_id(sys.argv[1])
    meta = fetch_metadata(vid)
    tr = fetch_transcript(vid)
    print(f"{vid} | {meta.title} | {meta.channel_name}")
    print(f"lang={tr.language_code} generated={tr.is_generated} segments={len(tr.segments)}")
    for s in tr.segments[:3]:
        print(f"  [{s.start:7.2f} +{s.duration:5.2f}] {s.text}")
except AppError as e:
    print(f"AppError {e.status_code} {e.error}: {e.message}")
