"""Basic RAG: select transcript context -> grounded prompt -> Groq -> answer + cited sources.

Context selection: if the whole transcript fits FULL_CONTEXT_MAX_TOKENS, every chunk is passed, so
nothing relevant can be missed; otherwise the TOP_K most similar chunks. Similarity only ranks
context: it does not decide whether the video contains the answer. That decision belongs to the
model, which must reply INSUFFICIENT_CONTEXT when the excerpts don't support an answer (in testing,
the similarity score could not separate answerable from absent questions; the model could).

Citations: excerpts are numbered [C1].. in the prompt; the model cites them; only cited excerpts
become sources, unknown ids are dropped, and the [Cn] markers are replaced with timestamps rendered
from stored data, so every timestamp shown is real.
"""
import re
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.db.repositories import ChunkRepository
from app.prompts.rag import (
    CLARIFY_MARKER,
    DEFAULT_CLARIFICATION,
    INSUFFICIENT_MARKER,
    NO_CONTEXT_ANSWER,
    SYSTEM_PROMPT,
    build_user_message,
    format_timestamp,
)
from app.schemas.chunk import RetrievedChunk
from app.services import llm
from app.services.question_intent import refers_back
from app.services.retrieval import retrieve

CHARS_PER_TOKEN = 4  # rough English average; only used to decide whether the transcript fits
FALLBACK_SOURCES = 2  # grounded answer without usable citations: show the most similar excerpts

# [C2] [C1, C3] [C1][C3] [C1-C3] [C1 and C3] [c2], and the full-width brackets some models emit: 【C2】
_CITATION = re.compile(r"[\[【]\s*(C\d+(?:\s*(?:[,;–-]|and)\s*C\d+)*)\s*[\]】]", re.IGNORECASE)
_CITATION_REF = re.compile(r"C(\d+)(?:\s*[–-]\s*C(\d+))?", re.IGNORECASE)
MAX_CITATION_RANGE = 10  # [C1-C99] is a model glitch, not 99 citations


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    sources: list[RetrievedChunk] = field(default_factory=list)
    grounded: bool = True  # False when the transcript did not contain the answer
    mode: str = "retrieval"  # "full" (whole transcript as context) | "retrieval" (top-k)
    kind: str = "answer"  # "answer" | "refusal" | "clarification" (asked the user what they meant)


def select_context(video_id: str, question: str, chunk_repo=None, model=None, top_k: int | None = None):
    """Return (chunks in video order, mode)."""
    repo = chunk_repo or ChunkRepository()
    settings = get_settings()
    all_chunks = repo.list_for_video(video_id)
    if not all_chunks:
        return [], "full"
    estimated_tokens = sum(len(c["content"]) for c in all_chunks) / CHARS_PER_TOKEN
    if estimated_tokens <= settings.full_context_max_tokens:
        # Score every chunk (needed for citation fallback); all of them become context.
        hits, mode = retrieve(video_id, question, top_k=len(all_chunks), chunk_repo=repo, model=model), "full"
    else:
        hits, mode = retrieve(video_id, question, top_k=top_k or settings.top_k, chunk_repo=repo, model=model), "retrieval"
    return sorted(hits, key=lambda c: (c.start_time is None, c.start_time or 0)), mode


def apply_citations(reply: str, context: list[RetrievedChunk]) -> tuple[str, list[RetrievedChunk]]:
    """Replace [Cn] markers with real timestamps; return (text, cited chunks in first-cited order).
    Ids that don't exist in the context are removed, never shown."""
    cited: list[RetrievedChunk] = []

    def render(match: re.Match) -> str:
        stamps = []
        numbers = []
        for ref in _CITATION_REF.finditer(match.group(1)):
            first = int(ref.group(1))
            last = int(ref.group(2) or first)
            numbers.extend(range(first, last + 1) if 0 <= last - first < MAX_CITATION_RANGE else [first])
        for number in numbers:
            index = number - 1
            if 0 <= index < len(context):
                chunk = context[index]
                if chunk not in cited:
                    cited.append(chunk)
                stamps.append(f"{format_timestamp(chunk.start_time)}–{format_timestamp(chunk.end_time)}")
        return f"[{', '.join(stamps)}]" if stamps else ""

    text = _CITATION.sub(render, reply)
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)  # tidy spaces left by removed markers
    return text.strip(), cited


def _clarification(reply: str) -> str:
    text = reply.split(CLARIFY_MARKER, 1)[1].lstrip(" :\n-").strip()
    return text if text else DEFAULT_CLARIFICATION


def answer_question(
    video_id: str,
    question: str,
    top_k: int | None = None,
    chunk_repo=None,
    model=None,
    llm_client=None,
    history: list[dict] | None = None,
    retrieval_query: str | None = None,
    interpreted: str | None = None,
) -> RagAnswer:
    """`question` is the user's own words. `history` is this session's recent messages (shown to the
    model to understand references, never as evidence). `retrieval_query` is what the transcript is
    searched with (defaults to the question); `interpreted` is the follow-up rewrite, shown as a guess."""
    context, mode = select_context(
        video_id, retrieval_query or question, chunk_repo=chunk_repo, model=model, top_k=top_k
    )
    if not context:  # no transcript stored: nothing to answer from
        return RagAnswer(answer=NO_CONTEXT_ANSWER, sources=[], grounded=False, mode=mode, kind="refusal")

    prompt = build_user_message(context, question, history=history, interpreted=interpreted)
    reply = llm.generate(SYSTEM_PROMPT, prompt, llm=llm_client)
    if CLARIFY_MARKER in reply:
        if refers_back(question):  # an unresolved reference: ask, don't guess
            return RagAnswer(answer=_clarification(reply), sources=[], grounded=False, mode=mode, kind="clarification")
        # A clear question has nothing to clarify; the model just didn't find it: a normal refusal.
        return RagAnswer(answer=NO_CONTEXT_ANSWER, sources=[], grounded=False, mode=mode, kind="refusal")
    if INSUFFICIENT_MARKER in reply:  # the model judged the transcript insufficient
        return RagAnswer(answer=NO_CONTEXT_ANSWER, sources=[], grounded=False, mode=mode, kind="refusal")

    text, sources = apply_citations(reply, context)
    if not sources:  # answered without usable citations: show the most similar excerpts
        sources = sorted(context, key=lambda c: c.similarity, reverse=True)[:FALLBACK_SOURCES]
    return RagAnswer(answer=text, sources=sources, grounded=True, mode=mode)
