"""Decide whether a chat question asks about the video as a whole (answered from the stored
Insights) or about something specific (answered by normal transcript retrieval).

Deterministic on purpose: no extra LLM call, easy to test. A question is "broad" only if it matches
an overview pattern AND nothing specific is left once those words and generic filler are removed,
so "summarise the part about pronunciation" stays on the strict retrieval path.
"""
import re

OVERVIEW = "overview"  # summary + topics
POINTS = "points"  # key takeaways

_POINTS_PATTERNS = [
    r"\b(main|key|important|major|core)\s+(points?|takeaways?|ideas?|lessons?|learnings?)\b",
    r"\btake\s*aways?\b",
    r"\bhighlights\b",
]
_OVERVIEW_PATTERNS = [
    # "what is the video about" and the statement order "what the video is about"
    r"\bwhat\s+((is|s)\s+)?(this|the|it)(\s+(video|clip))?(\s+(is|s))?\s+(all\s+)?about\b",
    r"\bsumm(ary|aries|arise|arize|arised|arized|arising|arizing)\b",
    r"\bsum\s+(it|this|that)?\s*up\b",
    r"\boverview\b",
    r"\bgist\b",
    r"\btl\s?dr\b",
    r"\brecap\b",
    r"\bwhat\s+(does|do)\s+(this|the|it)(\s+(video|clip))?\s+(cover|discuss|talk\s+about)\b",
    r"\bwhat\s+(is|are)\s+(covered|discussed)\b",
    r"\b(main|key|central)\s+(topics?|ideas?|message|theme|point)\b",
    r"\bwhat\s+topics\b",
    r"\btopics?\s+(are\s+)?(covered|discussed)\b",
]

# Words that carry no subject of their own in a request about the whole video.
_FILLER = set(
    """a an the this that it its video clip whole entire full overall general short brief quick
    of for in on to about from with please can could would will you your give me us i we want
    need tell provide write make show explain describe do does did is are be was what s so just
    some few all basically there here really in briefly shortly words covered discussed""".split()
)


def _normalise(text: str) -> str:
    text = (text or "").lower().replace("’", "'").replace("'", " ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_REFERENCES = {"it", "its", "that", "those", "them", "they", "he", "she", "him", "her", "his", "these"}


def refers_back(question: str) -> bool:
    """True if the message leans on earlier conversation ("summarise it", "what's that about")."""
    words = _normalise(question).split()
    for i, w in enumerate(words):
        if w in _REFERENCES:
            return True
        if w == "this" and (i + 1 >= len(words) or words[i + 1] not in ("video", "clip")):
            return True
    return False


def route(message: str, standalone: str) -> str | None:
    """Intent for a chat turn. A self-contained message is classified as typed, so the follow-up
    rewrite cannot push "Give me an overview" off the summary path by adding words. A message that
    refers back ("summarise it") is classified by its rewritten, standalone form."""
    return classify(standalone) if refers_back(message) else classify(message)


def classify(question: str) -> str | None:
    """Return OVERVIEW or POINTS for a whole-video question, else None (use normal retrieval)."""
    text = _normalise(question)
    if not text:
        return None
    intent = None
    remainder = text
    for kind, patterns in ((POINTS, _POINTS_PATTERNS), (OVERVIEW, _OVERVIEW_PATTERNS)):
        for pattern in patterns:
            if re.search(pattern, remainder):
                intent = intent or kind
                remainder = re.sub(pattern, " ", remainder)
    if intent is None:
        return None
    leftover = [w for w in remainder.split() if w not in _FILLER]
    return intent if not leftover else None
