"""Manual end-to-end check with a real YouTube video (not part of the test suite).

Usage (venv active):  python scripts/try_rag.py <youtube_url> "<question>" ["<question>" ...]
Ingests the video temporarily into Supabase, asks the questions through Groq, then deletes it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.errors import AppError  # noqa: E402
from app.db.repositories import VideoRepository  # noqa: E402
from app.prompts.rag import format_timestamp  # noqa: E402
from app.services.chunking import chunk_transcript  # noqa: E402
from app.services.rag import answer_question  # noqa: E402
from app.services.retrieval import store_chunks  # noqa: E402
from app.services.transcript import fetch_transcript  # noqa: E402
from app.services.youtube import extract_video_id, fetch_metadata  # noqa: E402

url, questions = sys.argv[1], sys.argv[2:]
videos = VideoRepository()
vid = extract_video_id(url)
meta = fetch_metadata(vid)
row = videos.upsert_from_metadata(meta)
try:
    n = store_chunks(row["id"], chunk_transcript(fetch_transcript(vid)))
    print(f"{meta.title}: {n} chunks stored\n")
    for q in questions:
        print(f"Q: {q}")
        try:
            out = answer_question(row["id"], q)
            print(f"A: {out.answer}")
            print(f"   grounded={out.grounded}")
            for s in out.sources:
                print(f"   source {format_timestamp(s.start_time)}-{format_timestamp(s.end_time)} "
                      f"sim={s.similarity:.2f}: {s.content[:70]}...")
        except AppError as e:
            print(f"   AppError {e.status_code} {e.error}: {e.message}")
        print()
finally:
    videos.client.table("videos").delete().eq("id", row["id"]).execute()
    print("cleaned up")
