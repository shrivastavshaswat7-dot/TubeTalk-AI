"""Google sign-in through Supabase Auth (OAuth 2.0 with PKCE), done on the Streamlit server.

1. "Continue with Google" links to Supabase's /authorize with a PKCE code challenge. The matching
   code verifier never leaves this server: it is kept here, keyed by a random one-time `auth_state`
   that is added to the return address. Each state works once; the landing page swaps its link for a
   new one as soon as the old state is used (e.g. by a sign-in in another tab) or the link gets old.
2. Google -> Supabase -> back to APP_URL?auth_state=…&code=…. The code and the verifier are exchanged
   for a Supabase session (access + refresh token), kept only in this browser session's
   st.session_state. The code is removed from the address bar straight away.
3. The access token goes with every backend request (api_client) and is refreshed shortly before it
   expires. A 401 from the backend, or a refresh that fails, ends the session.

Streamlit cannot set cookies, so a full page reload starts a new browser session and the user signs
in again (one click: Google remembers them). Tokens are never put in a URL or logged.
"""
import base64
import hashlib
import secrets
import threading
import time
from urllib.parse import urlencode

import requests
import streamlit as st

import state
from config import get_setting

KEY_SESSION = "auth_session"  # {"access_token", "refresh_token", "expires_at", "user": {...}}
KEY_LOGIN_URL = "auth_login_url"  # (created_at, auth_state, url) prepared for this browser session

# A sign-in link carries a one-time auth_state. It is valid for PENDING_TTL_SECONDS after the link was
# drawn, and the landing page redraws its link (LINK_CHECK_SECONDS) once the link is older than
# LINK_MAX_AGE_SECONDS or its state has been used — e.g. in another tab that already signed in. So the
# link on screen is always unused and leaves at least MIN_SIGN_IN_SECONDS to finish on Google's page.
PENDING_TTL_SECONDS = 900
LINK_MAX_AGE_SECONDS = 120
LINK_CHECK_SECONDS = 30
MIN_SIGN_IN_SECONDS = PENDING_TTL_SECONDS - LINK_MAX_AGE_SECONDS - LINK_CHECK_SECONDS  # 12.5 minutes
REFRESH_MARGIN_SECONDS = 60  # refresh the access token this long before it expires
TIMEOUT_SECONDS = 15

EXPIRED_MESSAGE = "Your session has expired. Please sign in again."
SIGNED_OUT_MESSAGE = "You've signed out."


# ── PKCE and pending sign-ins ─────────────────────────────────────────────────


def code_challenge(verifier: str) -> str:
    """RFC 7636 S256: base64url(sha256(verifier)) without padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@st.cache_resource
def _pending_store() -> dict:
    """Process-wide: the browser returns from Google in a new Streamlit session."""
    return {"lock": threading.Lock(), "items": {}}


def _remember(auth_state: str, verifier: str) -> None:
    store, now = _pending_store(), time.time()
    with store["lock"]:
        for key in [k for k, (at, _) in store["items"].items() if now - at > PENDING_TTL_SECONDS]:
            del store["items"][key]
        store["items"][auth_state] = (now, verifier)


def _is_pending(auth_state: str) -> bool:
    """True while this state is unused and fresh (a read only: it is not consumed)."""
    store = _pending_store()
    with store["lock"]:
        item = store["items"].get(auth_state)
    return item is not None and time.time() - item[0] <= PENDING_TTL_SECONDS


def _take(auth_state: str) -> str | None:
    """The verifier for this sign-in, at most once and only while it is fresh."""
    store = _pending_store()
    with store["lock"]:
        item = store["items"].pop(auth_state, None)
    if item is None or time.time() - item[0] > PENDING_TTL_SECONDS:
        return None
    return item[1]


# ── Supabase Auth calls ───────────────────────────────────────────────────────


def _auth_url(path: str) -> str:
    return f"{get_setting('SUPABASE_URL').rstrip('/')}/auth/v1/{path}"


def _headers(access_token: str | None = None) -> dict:
    headers = {"apikey": get_setting("SUPABASE_PUBLISHABLE_KEY")}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def _session_from(data) -> dict | None:
    """Keep only what the app needs from a Supabase token response."""
    if not isinstance(data, dict):
        return None
    user = data.get("user") or {}
    if not (data.get("access_token") and data.get("refresh_token") and user.get("id")):
        return None
    meta = user.get("user_metadata") or {}
    try:
        expires_at = float(data.get("expires_at") or time.time() + float(data.get("expires_in") or 3600))
    except (TypeError, ValueError):
        expires_at = time.time() + 3600
    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": expires_at,
        "user": {
            "id": user["id"],
            "email": user.get("email"),
            "name": meta.get("full_name") or meta.get("name") or user.get("email") or "Signed in",
        },
    }


def _token_request(grant_type: str, payload: dict) -> dict | None:
    try:
        resp = requests.post(
            _auth_url("token"), params={"grant_type": grant_type}, json=payload,
            headers=_headers(), timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return None
    if not resp.ok:
        return None
    try:
        return _session_from(resp.json())
    except ValueError:
        return None


# ── Session lifecycle ─────────────────────────────────────────────────────────


def login_url() -> str:
    """The "Continue with Google" address for this browser session.

    Reused only while it is recent AND its one-time state is still unused. A state used by a sign-in
    (in this tab or another one) is never offered again; an older link is replaced by a new one, while
    its own state stays valid until it expires, for a sign-in already in progress on Google's page."""
    cached = st.session_state.get(KEY_LOGIN_URL)
    if (cached and len(cached) == 3 and time.time() - cached[0] < LINK_MAX_AGE_SECONDS
            and _is_pending(cached[1])):
        return cached[2]
    verifier = secrets.token_urlsafe(64)
    auth_state = secrets.token_urlsafe(24)
    _remember(auth_state, verifier)
    return_to = f"{get_setting('APP_URL').rstrip('/')}/?{urlencode({'auth_state': auth_state})}"
    url = _auth_url("authorize") + "?" + urlencode({
        "provider": "google",
        "redirect_to": return_to,
        "code_challenge": code_challenge(verifier),
        "code_challenge_method": "s256",
    })
    st.session_state[KEY_LOGIN_URL] = (time.time(), auth_state, url)
    return url


def handle_callback() -> str | None:
    """Finish a sign-in if this page load is the return from Google. Returns an error to show, or None."""
    params = st.query_params
    code, auth_state, error = params.get("code"), params.get("auth_state"), params.get("error")
    if not (code or auth_state or error):
        return None
    st.query_params.clear()  # never leave the one-time code in the address bar
    # Whatever happens next, this tab's next sign-in starts with a brand-new link and state.
    st.session_state.pop(KEY_LOGIN_URL, None)
    if error or not code:
        return "Google sign-in was cancelled or didn't complete. Please try again."
    verifier = _take(auth_state) if auth_state else None  # strictly single use
    if verifier is None:
        return ("That sign-in link has expired or was already used. A fresh one is ready: select "
                "Continue with Google to sign in again.")
    session = _token_request("pkce", {"auth_code": code, "code_verifier": verifier})
    if session is None:
        return "Sign-in couldn't be completed. Please try again."
    _start(session)
    return None


def _clear_app_state() -> None:
    """Forget everything cached for the previous user (videos, sessions, messages, insights…)."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def _start(session: dict) -> None:
    previous = (st.session_state.get(KEY_SESSION) or {}).get("user", {}).get("id")
    if previous != session["user"]["id"]:
        _clear_app_state()
    st.session_state[KEY_SESSION] = session


def current_session() -> dict | None:
    """The signed-in session, refreshed if it is about to expire; None when signed out."""
    session = st.session_state.get(KEY_SESSION)
    if not session:
        return None
    if session["expires_at"] - time.time() > REFRESH_MARGIN_SECONDS:
        return session
    refreshed = _token_request("refresh_token", {"refresh_token": session["refresh_token"]})
    if refreshed is None:
        if session["expires_at"] > time.time():
            return session  # refresh failed (e.g. a network blip) but the token still works: retry later
        end_session(EXPIRED_MESSAGE)
        return None
    if refreshed["user"]["id"] != session["user"]["id"]:
        end_session(EXPIRED_MESSAGE)
        return None
    st.session_state[KEY_SESSION] = refreshed
    return refreshed


def access_token() -> str | None:
    session = current_session()
    return session["access_token"] if session else None


def user() -> dict | None:
    session = st.session_state.get(KEY_SESSION)
    return session["user"] if session else None


def end_session(message: str | None = None) -> None:
    """Sign out locally: drop the tokens and every cached item of this user."""
    _clear_app_state()
    if message:
        state.flash(message)


def session_expired() -> None:
    """The backend rejected our token (401): back to the landing page with a clear message."""
    end_session(EXPIRED_MESSAGE)
    st.query_params.clear()
    st.rerun()


def sign_out() -> None:
    session = st.session_state.get(KEY_SESSION)
    if session:
        try:  # best effort: revoke the refresh token at Supabase too
            requests.post(_auth_url("logout"), params={"scope": "local"},
                          headers=_headers(session["access_token"]), timeout=TIMEOUT_SECONDS)
        except requests.RequestException:
            pass
    end_session(SIGNED_OUT_MESSAGE)
    st.query_params.clear()
    st.rerun()
