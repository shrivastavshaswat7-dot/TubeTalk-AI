"""RAG evaluation on a processed video (manual check, not part of the test suite).

Runs labelled questions through the real answer pipeline with real retrieval and the real LLM.
Nothing is written to the database: follow-up history is kept in memory.

Usage (venv active, from the repo root):
    python scripts/eval_rag.py [youtube_video_id]

Metrics:
  answered      answerable questions that got a grounded answer
  refused       absent questions that were correctly refused
  cited_right   grounded answers whose sources include a chunk that really contains the answer
  extra_sources sources that are not among the expected chunks (noise shown to the user)
  follow-ups    run through the same per-turn flow as the chat endpoint (history, rewrite,
                retrieval query); "clarify" labels expect a clarifying question, and
                "refuse_or_clarify" labels accept either a refusal or a clarifying question.

    python scripts/eval_rag.py [youtube_video_id] [--followups]   (--followups: skip single questions)
"""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

from app.core.errors import AppError  # noqa: E402
from app.db.repositories import VideoRepository  # noqa: E402
from app.services import chat as chat_service  # noqa: E402
from app.services.chat import contextualize_question  # noqa: E402
from app.services.rag import answer_question  # noqa: E402

# Labelled set for "Give me 2 Minutes... I'll remove your Fear of Speaking English" (a3fPGUGC6w4).
# expected = chunk_index values whose text contains the answer (None = absent from the video).
EVAL_SETS = {
    "a3fPGUGC6w4": {
        "single": [
            ("Why does the speaker mention Katrina Kaif?", {0}),
            ("What should I do if I'm scared of being judged?", {0}),
            ("What are the three steps the speaker recommends?", {0, 1}),
            ("Does the video mention ChatGPT?", {1}),
            ("Does this video talk about AI?", {1}),
            ("ChatGPT", {1}),
            ("which apps can check my grammar?", {1}),
            ("What tools does the speaker recommend?", {1}),
            ("How long should each practice session be?", {1}),
            ("How long does it take to see improvement?", {1, 2}),
            ("Why should I keep my sentences short?", {2}),
            ("How do I prepare for the IELTS exam?", None),
            ("Does the speaker recommend watching English movies?", None),
            ("How much does ChatGPT Plus cost?", None),
            ("What is the capital of France?", None),
            ("What is the speaker's favourite movie?", None),
        ],
        "followups": [
            [("What tools does the speaker recommend?", {1}), ("How do I use them?", {1}),
             ("Is there a time limit?", {1})],
            [("Why does the speaker mention Katrina Kaif?", {0}), ("Why does he bring her up?", {0})],
            [("Why does the speaker mention Katrina Kaif?", {0}), ("Why does he mention her?", {0})],
            [("What are the three steps the speaker recommends?", {0, 1}),
             ("Tell me more about the second one.", {0, 1})],
            [("What tools does the speaker recommend?", {1}), ("How much do they cost?", None)],
            [("which apps can check my grammar?", {1}), ("Which one is better?", "refuse_or_clarify")],
            [("What did he say about that?", "clarify")],
        ],
    }
}


def ask(video_id, question):
    for wait in (0, 10, 30, 60):
        time.sleep(wait)
        try:
            return answer_question(video_id, question)
        except AppError as exc:
            if exc.error != "LLM_RATE_LIMITED":
                raise
    raise RuntimeError("rate limited")


def kind_of(out):
    return getattr(out, "kind", "answer" if out.grounded else "refusal")


def turn(video_id, question, history):
    """One chat turn as the chat endpoint does it (falls back to the older flow if absent)."""
    if hasattr(chat_service, "answer_turn"):
        for wait in (0, 10, 30, 60):
            time.sleep(wait)
            try:
                standalone, retrieval_query, out = chat_service.answer_turn(video_id, question, history)
                return f"{standalone!r} search={retrieval_query!r}", out
            except AppError as exc:
                if exc.error != "LLM_RATE_LIMITED":
                    raise
        raise RuntimeError("rate limited")
    standalone = contextualize_question(question, history)
    return repr(standalone), ask(video_id, standalone)


def judge(out, expected):
    cited = {s.chunk_index for s in out.sources}
    if expected == "clarify":
        return ("ok" if kind_of(out) == "clarification" else "NO-CLARIFY"), cited, 0
    if expected == "refuse_or_clarify":
        return ("ok" if not out.grounded else "GUESSED"), cited, 0
    if expected is None:
        return ("ok" if not out.grounded else "INVENTED"), cited, 0
    if not out.grounded:
        return "MISSED", cited, 0
    extra = len(cited - expected)
    return ("ok" if cited & expected else "WRONG-CITE"), cited, extra


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    yt_id = args[0] if args else "a3fPGUGC6w4"
    labels = EVAL_SETS[yt_id]
    video_id = VideoRepository().get_by_youtube_id(yt_id)["id"]
    stats = {"answerable": 0, "answered": 0, "absent": 0, "refused": 0, "cited_right": 0, "extra": 0,
             "sources": 0, "ambiguous": 0, "handled": 0}

    def record(question, out, expected, prefix=""):
        verdict, cited, extra = judge(out, expected)
        if expected in ("clarify", "refuse_or_clarify"):
            stats["ambiguous"] += 1
            stats["handled"] += verdict == "ok"
        elif expected is None:
            stats["absent"] += 1
            stats["refused"] += not out.grounded
        else:
            stats["answerable"] += 1
            stats["answered"] += out.grounded
            stats["cited_right"] += verdict == "ok"
            stats["extra"] += extra
            stats["sources"] += len(out.sources)
        shown = sorted(expected) if isinstance(expected, set) else (expected or "-")
        print(f"{prefix}{verdict:10} [{kind_of(out)}] cited={sorted(cited)} expected={shown}  {question}")
        print(f"{prefix}           {out.answer[:150]!r}")

    if "--followups" not in sys.argv:
        print("SINGLE QUESTIONS")
        for question, expected in labels["single"]:
            record(question, ask(video_id, question), expected)

    print("\nFOLLOW-UPS (history in memory)")
    for convo in labels["followups"]:
        history = []
        for question, expected in convo:
            how, out = turn(video_id, question, history)
            record(f"{question}  ->  {how}", out, expected, prefix="  ")
            history += [{"role": "user", "content": question}, {"role": "assistant", "content": out.answer}]

    s = stats
    print("\nSUMMARY")
    print(f"  answered (answerable grounded) : {s['answered']}/{s['answerable']}")
    print(f"  refused  (absent refused)      : {s['refused']}/{s['absent']}")
    print(f"  cited a correct chunk          : {s['cited_right']}/{s['answered']} grounded answers")
    print(f"  extra (non-expected) sources   : {s['extra']} of {s['sources']} sources shown")
    print(f"  ambiguous handled (no guessing): {s['handled']}/{s['ambiguous']}")


if __name__ == "__main__":
    main()
