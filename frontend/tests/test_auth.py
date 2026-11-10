"""Google sign-in through Supabase Auth: landing page, return from Google, refresh, expiry and sign-out.
Supabase Auth and the backend are never called: requests.post / requests.request are replaced."""
import html
import re
import time
from pathlib import Path
from types import SimpleNamespace as NS
from urllib.parse import parse_qs, urlparse

import pytest
from streamlit.testing.v1 import AppTest

import api_client
import auth

APP = str(Path(__file__).resolve().parents[1] / "app.py")
USER = {"id": "aaaaaaaa-0000-4000-8000-00000000000a", "email": "ada@example.com",
        "user_metadata": {"full_name": "Ada Lovelace"}}
OTHER = {"id": "bbbbbbbb-0000-4000-8000-00000000000b", "email": "bob@example.com", "user_metadata": {}}


def token_response(access="access-1", refresh="refresh-1", user=USER, expires_in=3600):
    return {"access_token": access, "refresh_token": refresh, "expires_in": expires_in,
            "expires_at": int(time.time()) + expires_in, "token_type": "bearer", "user": user}


def session(access="access-0", expires_at=None, user_id=USER["id"]):
    return {"access_token": access, "refresh_token": "refresh-0",
            "expires_at": expires_at if expires_at is not None else time.time() + 3600,
            "user": {"id": user_id, "email": "ada@example.com", "name": "Ada Lovelace"}}


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code, self.ok, self._body = status, status < 400, body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body

    @property
    def reason(self):
        return "x"


@pytest.fixture
def supabase(monkeypatch):
    """Fake Supabase Auth: records every call; `respond(grant)` decides the answer."""
    s = NS(calls=[], responses={})

    def post(url, params=None, json=None, headers=None, timeout=None):
        s.calls.append(NS(url=url, params=params or {}, json=json, headers=headers or {}))
        key = (params or {}).get("grant_type") or url.rsplit("/", 1)[-1]
        return s.responses.get(key, FakeResp(204))

    monkeypatch.setattr(auth.requests, "post", post)
    return s


@pytest.fixture
def backend(monkeypatch):
    """Patched backend calls (the dashboard's); records which were made."""
    calls = []

    def fake(name, result):
        def _f(*args, **kwargs):
            calls.append(name)
            return result
        monkeypatch.setattr(api_client, name, _f)

    fake("check_health", (True, "TubeTalk AI"))
    fake("list_videos", {"success": True, "videos": []})
    return calls


def run(query=None, preset=None):
    at = AppTest.from_file(APP, default_timeout=30)
    for key, value in (query or {}).items():
        at.query_params[key] = value
    for key, value in (preset or {}).items():
        at.session_state[key] = value
    at.run()
    return at


def texts(at):
    out = [str(e.value) for coll in (at.markdown, at.caption, at.error, at.info) for e in coll]
    return "\n".join(out)


def google_link(at) -> str:
    for m in at.markdown:
        match = re.search(r'class="tt-google" href="([^"]+)"', str(m.value))
        if match:
            return html.unescape(match.group(1))
    raise AssertionError("no Google sign-in link on the page")


def signed_in(at) -> bool:
    return bool(at.session_state["auth_session"]) if "auth_session" in at.session_state else False


# ── PKCE and the sign-in link ────────────────────────────────────────────────


def test_pkce_challenge_is_s256():
    """RFC 7636 S256: base64url(sha256(verifier)), no padding — checked against an independent computation."""
    import base64
    import hashlib

    verifier = "a-verifier-of-sufficient-length-0123456789-abcdefghijklmnopqrstu"
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    challenge = auth.code_challenge(verifier)
    assert challenge == expected and len(challenge) == 43 and re.fullmatch(r"[A-Za-z0-9_-]+", challenge)


def test_signed_out_visitors_see_the_landing_page_and_nothing_is_called(supabase, backend):
    at = run()
    assert not at.exception
    page = texts(at)
    assert "Talk to any YouTube video." in page and "How it works" in page
    assert not at.text_input  # not the dashboard (no link form)
    assert backend == [] and supabase.calls == []
    assert not at.sidebar.button  # no conversations, videos or sign-out


def test_brand_lockup_on_landing_and_signed_in_sidebar(supabase, backend):
    lockup = 'TubeTalk<span class="tt-wordmark-ai">AI</span>'
    landing = "\n".join(str(m.value) for m in run().markdown)
    assert lockup in landing and 'class="tt-logo" src="data:image/svg+xml;base64,' in landing
    at = run(preset={"auth_session": session()})
    assert lockup in "\n".join(str(m.value) for m in at.sidebar.markdown)


def test_profile_name_is_escaped_in_the_account_block(supabase, backend):
    hostile = session()
    hostile["user"]["name"] = '<img src=x onerror="alert(1)">'
    at = run(preset={"auth_session": hostile})
    account = "\n".join(str(m.value) for m in at.sidebar.markdown)
    assert "&lt;img src=x" in account and "<img src=x" not in account


def test_sign_in_link_opens_a_new_tab(supabase, backend):
    """Streamlit Cloud's sandboxed frame can't navigate the page, and Google won't load in a frame."""
    page = "\n".join(str(m.value) for m in run().markdown)
    assert re.search(r'class="tt-google" href="[^"]+" target="_blank" rel="noopener"', page)


def test_sign_in_link_uses_pkce_and_a_one_time_state(supabase, backend):
    url = urlparse(google_link(run()))
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://project.supabase.test/auth/v1/authorize"
    assert q["provider"] == "google" and q["code_challenge_method"] == "s256"
    back = urlparse(q["redirect_to"])
    assert f"{back.scheme}://{back.netloc}" == "http://app.test"
    state_value = parse_qs(back.query)["auth_state"][0]
    verifier = auth._take(state_value)  # kept on the server, not in the link
    assert verifier and verifier not in google_link(run()) and auth.code_challenge(verifier) == q["code_challenge"]
    assert auth._take(state_value) is None  # one use only


def link_state(at) -> str:
    redirect_to = parse_qs(urlparse(google_link(at)).query)["redirect_to"][0]
    return parse_qs(urlparse(redirect_to).query)["auth_state"][0]


def age_pending(state_value: str, seconds: float) -> None:
    """Pretend this sign-in was started `seconds` ago (the clock itself is left alone)."""
    store = auth._pending_store()
    with store["lock"]:
        started, verifier = store["items"][state_value]
        store["items"][state_value] = (started - seconds, verifier)


# ── Regression: a landing tab left open, and slow sign-ins ───────────────────


def test_open_landing_tab_redraws_while_its_link_is_unused_and_recent(supabase, backend):
    at = run()
    first = link_state(at)
    at.run()  # e.g. the periodic redraw of the sign-in link
    assert link_state(at) == first and auth._is_pending(first)


def test_reused_landing_tab_never_offers_a_state_already_used_in_another_tab(supabase, backend):
    """The reported bug: account 1 signs in from this tab's link (the sign-in finishes in a new tab);
    the original tab must then offer a NEW link for account 2, not the used one."""
    landing = run()
    used = link_state(landing)
    # The return from Google arrives in another tab (a new browser session):
    supabase.responses["pkce"] = FakeResp(200, token_response())
    other_tab = run({"code": "code-1", "auth_state": used})
    assert signed_in(other_tab) and not auth._is_pending(used)

    landing.run()  # the landing tab redraws its link
    fresh = link_state(landing)
    assert fresh != used and auth._is_pending(fresh)

    supabase.responses["pkce"] = FakeResp(200, token_response(user=OTHER))
    second = run({"code": "code-2", "auth_state": fresh})  # account 2 signs in with the new link
    assert signed_in(second) and second.session_state["auth_session"]["user"]["id"] == OTHER["id"]


def test_a_used_state_is_refused_the_second_time(supabase, backend):
    """Strictly single use: replaying a return from Google never signs in again."""
    auth._remember("state-once", "verifier-once")
    supabase.responses["pkce"] = FakeResp(200, token_response())
    assert signed_in(run({"code": "code-1", "auth_state": "state-once"}))
    replay = run({"code": "code-1", "auth_state": "state-once"})
    assert not signed_in(replay) and "expired or was already used" in texts(replay)
    assert [c.params for c in supabase.calls] == [{"grant_type": "pkce"}]  # exchanged only once


def test_old_link_is_replaced_but_a_sign_in_already_started_with_it_can_finish(supabase, backend):
    at = run()
    old = link_state(at)
    created, state_value, url = at.session_state[auth.KEY_LOGIN_URL]
    at.session_state[auth.KEY_LOGIN_URL] = (created - auth.LINK_MAX_AGE_SECONDS - 1, state_value, url)
    at.run()
    assert link_state(at) != old  # the page now offers a newer link…
    supabase.responses["pkce"] = FakeResp(200, token_response())
    assert signed_in(run({"code": "code-1", "auth_state": old}))  # …and the older one still works once


def test_slow_sign_in_on_googles_page_still_succeeds(supabase, backend):
    """Worst case: the link was redrawn just before it was clicked, then e.g. a password and 2FA."""
    assert auth.MIN_SIGN_IN_SECONDS >= 12 * 60
    at = run()
    state_value = link_state(at)
    age_pending(state_value, auth.LINK_MAX_AGE_SECONDS + auth.LINK_CHECK_SECONDS + 12 * 60)
    supabase.responses["pkce"] = FakeResp(200, token_response())
    assert signed_in(run({"code": "code-1", "auth_state": state_value}))


def test_expired_sign_in_offers_a_fresh_sign_in(supabase, backend):
    at = run()
    expired = link_state(at)
    age_pending(expired, auth.PENDING_TTL_SECONDS + 1)
    back = run({"code": "code-1", "auth_state": expired})
    assert not signed_in(back) and supabase.calls == []
    assert "expired or was already used" in texts(back) and "Continue with Google" in texts(back)
    fresh = link_state(back)
    assert fresh != expired and auth._is_pending(fresh)  # a brand-new, usable link right there


def test_failed_return_in_a_tab_drops_that_tabs_old_link(supabase, backend):
    """A tab that had a link cached and then receives a bad return starts over with a new state."""
    at = run()
    cached = link_state(at)
    at.query_params["code"] = "code-1"
    at.query_params["auth_state"] = "never-issued"
    at.run()
    assert "expired or was already used" in texts(at)
    assert link_state(at) != cached


# ── Returning from Google ────────────────────────────────────────────────────


def test_return_from_google_signs_in_and_opens_the_dashboard(supabase, backend):
    auth._remember("state-1", "verifier-1")
    supabase.responses["pkce"] = FakeResp(200, token_response())
    at = run({"code": "code-1", "auth_state": "state-1"},
             preset={"recent_videos": [{"id": "someone-elses"}]})  # stale cache from a previous user
    assert not at.exception
    exchange = supabase.calls[0]
    assert exchange.url == "https://project.supabase.test/auth/v1/token" and exchange.params == {"grant_type": "pkce"}
    assert exchange.json == {"auth_code": "code-1", "code_verifier": "verifier-1"}
    assert exchange.headers == {"apikey": "test-publishable-key"}
    assert signed_in(at) and at.session_state["auth_session"]["user"]["id"] == USER["id"]
    assert dict(at.query_params) == {}  # the one-time code is gone from the address bar
    assert "Your videos" in texts(at) and "list_videos" in backend  # dashboard, freshly loaded
    assert any(b.label == "Sign out" for b in at.sidebar.button)
    account = "\n".join(str(m.value) for m in at.sidebar.markdown)
    assert "Ada Lovelace" in account and "ada@example.com" in account  # name and email in the account block


@pytest.mark.parametrize("query,message", [
    ({"code": "code-1", "auth_state": "never-issued"}, "expired or was already used"),
    ({"code": "code-1"}, "expired or was already used"),
    ({"error": "access_denied", "auth_state": "x"}, "cancelled"),
])
def test_bad_or_cancelled_returns_never_sign_in(supabase, backend, query, message):
    at = run(query)
    assert not at.exception and message in texts(at)
    assert supabase.calls == [] and not signed_in(at) and backend == []
    assert dict(at.query_params) == {}


def test_failed_code_exchange_stays_signed_out(supabase, backend):
    auth._remember("state-2", "verifier-2")
    supabase.responses["pkce"] = FakeResp(400, {"error": "invalid_grant", "error_description": "secret detail"})
    at = run({"code": "code-2", "auth_state": "state-2"})
    page = texts(at)
    assert "couldn't be completed" in page and "secret detail" not in page
    assert not signed_in(at) and backend == []


# ── Token refresh and expiry ─────────────────────────────────────────────────


def test_token_about_to_expire_is_refreshed(supabase, backend):
    supabase.responses["refresh_token"] = FakeResp(200, token_response(access="access-new", refresh="refresh-new"))
    at = run(preset={"auth_session": session(expires_at=time.time() + 10)})
    refresh = supabase.calls[0]
    assert refresh.params == {"grant_type": "refresh_token"} and refresh.json == {"refresh_token": "refresh-0"}
    assert at.session_state["auth_session"]["access_token"] == "access-new"
    assert "Your videos" in texts(at)


def test_expired_session_that_cannot_refresh_returns_to_the_landing_page(supabase, backend):
    supabase.responses["refresh_token"] = FakeResp(400, {"error": "invalid_grant"})
    at = run(preset={"auth_session": session(expires_at=time.time() - 5), "recent_videos": [{"id": "v"}]})
    assert not signed_in(at) and at.session_state["recent_videos"] is None  # the cached list is gone
    assert "Talk to any YouTube video." in texts(at) and backend == []
    assert any("session has expired" in str(t.value) for t in at.toast)


def test_refresh_switching_to_another_user_is_refused(supabase, backend):
    supabase.responses["refresh_token"] = FakeResp(200, token_response(user=OTHER))
    at = run(preset={"auth_session": session(expires_at=time.time() + 10)})
    assert not signed_in(at) and backend == []


def test_backend_401_ends_the_session(supabase, monkeypatch):
    monkeypatch.setattr(api_client, "check_health", lambda: (True, "TubeTalk AI"))
    seen = []

    def request(method, url, timeout=None, headers=None, **kwargs):
        seen.append(headers)
        return FakeResp(401, {"success": False, "error": "AUTH_REQUIRED", "message": "Please sign in to continue."})

    monkeypatch.setattr(api_client.requests, "request", request)
    at = run(preset={"auth_session": session()})
    assert seen and seen[0] == {"Authorization": "Bearer access-0"}  # the token was sent
    assert not signed_in(at) and "Talk to any YouTube video." in texts(at)
    assert any("session has expired" in str(t.value) for t in at.toast)


# ── Sign out ─────────────────────────────────────────────────────────────────


def test_sign_out_revokes_and_forgets_everything(supabase, backend):
    at = run(preset={"auth_session": session(), "messages_v_s": [{"role": "user", "content": "private"}]})
    next(b for b in at.sidebar.button if b.label == "Sign out").click().run()
    logout = supabase.calls[-1]
    assert logout.url == "https://project.supabase.test/auth/v1/logout" and logout.params == {"scope": "local"}
    assert logout.headers == {"apikey": "test-publishable-key", "Authorization": "Bearer access-0"}
    assert not signed_in(at) and "messages_v_s" not in at.session_state
    assert "Talk to any YouTube video." in texts(at)
    assert any("signed out" in str(t.value) for t in at.toast)


def test_sign_out_still_works_if_supabase_is_unreachable(supabase, backend, monkeypatch):
    at = run(preset={"auth_session": session()})

    def down(*a, **k):
        raise auth.requests.ConnectionError("down")

    monkeypatch.setattr(auth.requests, "post", down)
    next(b for b in at.sidebar.button if b.label == "Sign out").click().run()
    assert not at.exception and not signed_in(at)


# ── API client and configuration ─────────────────────────────────────────────


def test_every_backend_request_carries_the_access_token(monkeypatch):
    seen = []
    monkeypatch.setattr(api_client.requests, "request",
                        lambda method, url, timeout=None, headers=None, **k: seen.append(headers) or FakeResp(200, {"videos": []}))
    monkeypatch.setattr(auth, "access_token", lambda: "tok-123")
    api_client.list_videos()
    api_client.get_messages("s", "v")
    api_client.chat("v", "s", "hi")
    assert seen == [{"Authorization": "Bearer tok-123"}] * 3


def test_no_token_means_no_authorization_header(monkeypatch):
    seen = []
    monkeypatch.setattr(api_client.requests, "request",
                        lambda method, url, timeout=None, headers=None, **k: seen.append(headers) or FakeResp(200, {}))
    monkeypatch.setattr(auth, "access_token", lambda: None)
    api_client.list_videos()
    assert seen == [{}]


@pytest.mark.parametrize("name", ["SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "APP_URL"])
def test_missing_sign_in_settings_show_a_configuration_error(supabase, backend, monkeypatch, name):
    monkeypatch.setenv(name, "  ")
    at = run()
    assert any(name in str(e.value) for e in at.error)
    assert supabase.calls == [] and backend == []
