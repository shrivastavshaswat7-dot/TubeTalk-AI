"""Manual tuning aid (not part of the test suite): print top similarities for questions the
video DOES and DOES NOT answer, to choose MIN_SIMILARITY.

Usage (venv active):  python scripts/tune_threshold.py <youtube_url>
Ingests the video temporarily into Supabase and deletes it afterwards.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.repositories import VideoRepository  # noqa: E402
from app.services.chunking import chunk_transcript  # noqa: E402
from app.services.retrieval import retrieve, store_chunks  # noqa: E402
from app.services.transcript import fetch_transcript  # noqa: E402
from app.services.youtube import extract_video_id, fetch_metadata  # noqa: E402

ANSWERABLE = [
    "What is a neuron in a neural network?",
    "How many layers does the example network have?",
    "What does the MNIST dataset contain?",
    "What is the purpose of the hidden layers?",
    "What are weights and biases?",
    "Why is the sigmoid function used?",
]
UNANSWERABLE = [
    "What is the capital of France?",
    "How do I bake sourdough bread?",
    "Who won the 2018 football World Cup?",
    "What is the best way to invest in the stock market?",
    "How do I change a flat tire?",
    "What is the recipe for chocolate cake?",
]

videos = VideoRepository()
vid = extract_video_id(sys.argv[1])
meta = fetch_metadata(vid)
tr = fetch_transcript(vid)
chunks = chunk_transcript(tr)
row = videos.upsert_from_metadata(meta)
try:
    n = store_chunks(row["id"], chunks)
    print(f"{meta.title}: {len(tr.segments)} segments -> {n} chunks\n")
    for label, questions in (("ANSWERABLE", ANSWERABLE), ("UNANSWERABLE", UNANSWERABLE)):
        print(label)
        for q in questions:
            hits = retrieve(row["id"], q, top_k=5)
            sims = ", ".join(f"{h.similarity:.2f}" for h in hits)
            print(f"  top={hits[0].similarity:.2f} [{sims}]  {q}")
        print()
finally:
    videos.client.table("videos").delete().eq("id", row["id"]).execute()
    print("cleaned up")
