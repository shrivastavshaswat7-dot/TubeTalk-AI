"""Manual check: real YouTube transcript -> real Groq insights. No database involved.

Usage (venv active):  python scripts/try_insights.py <youtube_url>
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.prompts.rag import format_timestamp  # noqa: E402
from app.services import insights as ins  # noqa: E402
from app.services.chunking import chunk_transcript  # noqa: E402
from app.services.transcript import fetch_transcript  # noqa: E402
from app.services.youtube import extract_video_id, fetch_metadata  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252

vid = extract_video_id(sys.argv[1])
meta = fetch_metadata(vid)
tr = fetch_transcript(vid)
chunks = [
    {"chunk_index": c.chunk_index, "content": c.content, "start_time": c.start_time, "end_time": c.end_time}
    for c in chunk_transcript(tr)
]
text_len = len(ins.chunks_to_text(chunks))
print(f"{meta.title}\n{len(chunks)} chunks, {text_len} chars, "
      f"{'single pass' if text_len <= ins.SINGLE_PASS_MAX_CHARS else str(len(ins.split_sections(chunks))) + ' sections (map-reduce)'}")

calls = []
real_generate = ins.llm.generate


def counting_generate(system, user, llm=None):
    calls.append(len(user))
    return real_generate(system, user, llm=llm)


ins.llm.generate = counting_generate
started = time.time()
data = ins.generate_insights(chunks, sleep=lambda s: (print(f"  (rate limited, waiting {s}s)"), time.sleep(s)))
print(f"\n{len(calls)} LLM calls, largest prompt {max(calls)} chars, {time.time() - started:.0f}s\n")
print("SUMMARY:\n" + data.summary + "\n")
print("KEY TAKEAWAYS:")
for t in data.key_takeaways:
    print(" -", t)
print("\nTOPICS:")
for t in data.topics:
    ts = format_timestamp(t["start_time"]) if t["start_time"] is not None else "--:--"
    print(f" [{ts}] {t['name']}")
