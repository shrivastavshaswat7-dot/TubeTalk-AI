"""Canonical error message mapping for ApiError codes."""
import streamlit as st

from api_client import ApiError

_CODE_MAP = {
    "BACKEND_UNREACHABLE":        "Can't reach the backend. Make sure it is running.",
    "TIMEOUT":                    "This is taking longer than expected. If the app was idle, the server may still be "
                                  "waking up, which can take about a minute. Please try again.",
    "INVALID_VIDEO_URL":          "Please enter a valid YouTube link.",
    "VIDEO_NOT_FOUND":            "That video doesn't exist or was removed.",
    "VIDEO_RESTRICTED":           "That video is private, age-restricted or unavailable.",
    # Not a network blip: YouTube refuses transcript requests from many cloud servers, so retrying
    # the same video rarely helps. Say so plainly and point at videos that already work.
    "YOUTUBE_BLOCKED":            "This video couldn't be processed: YouTube didn't allow this server to download its "
                                  "transcript. This is a YouTube restriction on cloud-hosted apps, not a problem with "
                                  "your link. Try another video, or open one of the ready videos below.",
    # Worded so it never suggests that someone else is processing the same video.
    "VIDEO_PROCESSING":           "This video is being prepared right now. Please try again in a minute.",
    "AUTH_REQUIRED":              "Your session has expired. Please sign in again.",
    "AUTH_UNAVAILABLE":           "Sign-in can't be checked right now. Please try again in a moment.",
    "PROCESSING_FAILED":          "The video couldn't be processed. Please try again.",
    "EMBEDDING_ERROR":            "The video couldn't be processed. Please try again.",
    "VIDEO_NOT_READY":            "This video hasn't finished processing.",
    "SESSION_NOT_FOUND":          "That conversation no longer exists.",
    "SESSION_VIDEO_MISMATCH":     "Something went wrong. Please return to Home and reopen the video.",
    "EMPTY_MESSAGE":              "Please enter a question.",
    "LLM_RATE_LIMITED":           "The AI service is busy. Wait a few seconds and try again.",
    "LLM_UNAVAILABLE":            "The AI service had a problem. Please try again.",
    "LLM_ERROR":                  "The AI service had a problem. Please try again.",
    "LLM_NOT_CONFIGURED":         "Something went wrong on our side. Please try again later.",
    "DATABASE_NOT_CONFIGURED":    "Something went wrong on our side. Please try again later.",
    "DATABASE_ERROR":             "Something went wrong on our side. Please try again later.",
    "INTERNAL_ERROR":             "Something went wrong on our side. Please try again later.",
    "INSIGHTS_GENERATING":        "Insights are being generated, please wait.",
    "INSIGHTS_NOT_READY":         "Insights haven't been generated for this video yet.",
    "SUMMARY_GENERATING":         "The video summary is still being prepared. Try again in a moment.",
    "INSIGHTS_FAILED":            "Couldn't generate insights for this video. Try again.",
    "VALIDATION_ERROR":           "That input isn't valid.",
}

# The backend's own wording is the clearest for these, so it is shown as-is. NETWORK_ERROR says
# which service couldn't be reached (YouTube or the transcript service).
_PASSTHROUGH = {"TRANSCRIPT_UNAVAILABLE", "UNSUPPORTED_LANGUAGE", "SUMMARY_UNAVAILABLE", "NETWORK_ERROR"}


def friendly_message(err: ApiError) -> str:
    if err.code in _PASSTHROUGH:
        return err.message  # use the API's own message
    return _CODE_MAP.get(err.code, err.message or "An unexpected error occurred.")


def show_error(err: ApiError):
    st.error(friendly_message(err))


def show_error_msg(code: str, message: str = ""):
    err = ApiError(code, message)
    st.error(friendly_message(err))
