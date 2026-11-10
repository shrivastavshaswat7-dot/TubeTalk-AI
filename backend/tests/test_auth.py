"""Access-token verification. Supabase is never called: get_client() is replaced by a fake whose
auth.get_claims returns or raises what each test needs."""
from types import SimpleNamespace as NS

import httpx
import pytest
from fastapi.security import HTTPAuthorizationCredentials
from supabase_auth.errors import AuthApiError, AuthInvalidJwtError, AuthRetryableError

from app.core import auth
from app.core.errors import AppError

USER_ID = "aaaaaaaa-0000-4000-8000-00000000000a"


def claims(**overrides):
    base = {"sub": USER_ID, "role": "authenticated", "aud": "authenticated", "email": "a@example.com"}
    base.update(overrides)
    return {"claims": base, "headers": {}, "signature": b""}


@pytest.fixture
def supabase(monkeypatch):
    state = NS(result=claims(), error=None, tokens=[])

    def get_claims(token):
        state.tokens.append(token)
        if state.error:
            raise state.error
        return state.result

    monkeypatch.setattr(auth, "get_client", lambda: NS(auth=NS(get_claims=get_claims)))
    return state


def bearer(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_valid_user_token(supabase):
    user = auth.get_current_user(bearer("good-token"))
    assert user == auth.CurrentUser(id=USER_ID, email="a@example.com")
    assert supabase.tokens == ["good-token"]


def test_audience_may_be_a_list(supabase):
    supabase.result = claims(aud=["authenticated", "other"])
    assert auth.get_current_user(bearer("t")).id == USER_ID


@pytest.mark.parametrize("credentials", [None, bearer(""), bearer("   ")])
def test_missing_token(supabase, credentials):
    with pytest.raises(AppError) as exc:
        auth.get_current_user(credentials)
    assert (exc.value.error, exc.value.status_code) == ("AUTH_REQUIRED", 401)
    assert supabase.tokens == []  # nothing to verify


@pytest.mark.parametrize("error", [
    AuthInvalidJwtError("Invalid JWT signature"),
    AuthApiError("invalid JWT", 401, None),
    ValueError("not a JWT"),
])
def test_invalid_expired_or_tampered_token(supabase, error):
    supabase.error = error
    with pytest.raises(AppError) as exc:
        auth.get_current_user(bearer("bad"))
    assert (exc.value.error, exc.value.status_code) == ("AUTH_REQUIRED", 401)
    assert "JWT" not in exc.value.message  # no internals in the response


@pytest.mark.parametrize("bad_claims", [
    claims(role="anon", aud=None),  # the public anon key
    claims(role="service_role"),  # the service-role key
    claims(aud="something-else"),
    claims(sub=None),
    claims(sub="not-a-uuid"),
])
def test_only_signed_in_user_tokens_are_accepted(supabase, bad_claims):
    supabase.result = bad_claims
    with pytest.raises(AppError) as exc:
        auth.get_current_user(bearer("t"))
    assert exc.value.error == "AUTH_REQUIRED"


def test_no_claims_returned(supabase):
    supabase.result = None
    with pytest.raises(AppError) as exc:
        auth.get_current_user(bearer("t"))
    assert exc.value.error == "AUTH_REQUIRED"


@pytest.mark.parametrize("error", [AuthRetryableError("down", 503), httpx.ConnectError("down")])
def test_auth_service_unreachable_is_not_reported_as_signed_out(supabase, error):
    supabase.error = error
    with pytest.raises(AppError) as exc:
        auth.get_current_user(bearer("t"))
    assert (exc.value.error, exc.value.status_code) == ("AUTH_UNAVAILABLE", 503)


def test_database_not_configured_passes_through(monkeypatch):
    def not_configured():
        raise AppError("DATABASE_NOT_CONFIGURED", "x", 503)

    monkeypatch.setattr(auth, "get_client", not_configured)
    with pytest.raises(AppError) as exc:
        auth.get_current_user(bearer("t"))
    assert exc.value.error == "DATABASE_NOT_CONFIGURED"
