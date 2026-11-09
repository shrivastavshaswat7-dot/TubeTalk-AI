"""Groq chat completion through langchain-groq, with errors mapped to AppError."""
import groq
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from app.core.config import get_settings
from app.core.errors import AppError


def _build_llm() -> ChatGroq:
    s = get_settings()
    if not s.groq_api_key or not s.groq_model or "your_" in s.groq_api_key or "your_" in s.groq_model:
        raise AppError(
            "LLM_NOT_CONFIGURED",
            "The language model is not configured. Set GROQ_API_KEY and GROQ_MODEL.",
            503,
        )
    kwargs = {}
    if s.groq_reasoning_effort:
        kwargs["reasoning_effort"] = s.groq_reasoning_effort
    return ChatGroq(
        model=s.groq_model,
        api_key=s.groq_api_key,
        temperature=s.groq_temperature,
        timeout=s.groq_timeout_seconds,
        max_tokens=s.groq_max_tokens,
        max_retries=1,
        **kwargs,
    )


def generate(system_prompt: str, user_message: str, llm=None) -> str:
    """Send one system+user exchange and return the text answer."""
    llm = llm or _build_llm()
    try:
        response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_message)])
    except groq.RateLimitError:
        raise AppError(
            "LLM_RATE_LIMITED", "The language model is busy right now. Please try again shortly.", 429
        )
    except (groq.APITimeoutError, groq.APIConnectionError):
        raise AppError("LLM_UNAVAILABLE", "Could not reach the language model. Please try again.", 503)
    except (groq.AuthenticationError, groq.PermissionDeniedError, groq.NotFoundError):
        # Bad key or retired model: a server configuration problem, not the user's.
        raise AppError("LLM_NOT_CONFIGURED", "The language model is not configured correctly.", 503)
    except Exception:
        raise AppError("LLM_ERROR", "Unable to generate a response at the moment.", 503)

    metadata = getattr(response, "response_metadata", None)
    if isinstance(metadata, dict) and metadata.get("finish_reason") == "length":
        # Never serve a silently truncated answer.
        raise AppError("LLM_ERROR", "The response was cut off. Please try again.", 503)

    text = response.content if isinstance(response.content, str) else ""
    if not text.strip():
        raise AppError("LLM_ERROR", "The language model returned an empty response.", 503)
    return text.strip()
