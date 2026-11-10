"""Supabase Auth: every API route except / and /health needs a signed-in user's access token.

The frontend signs users in with Google through Supabase Auth and sends the resulting access token
as `Authorization: Bearer <token>`. The token is verified with Supabase's own client: signature and
expiry against the project's signing keys (or by asking Supabase for older HS256 projects). Only
tokens issued to a signed-in user are accepted, so the public anon key or the service-role key can
never be used as a login.
"""
import uuid
from dataclasses import dataclass

import httpx
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase_auth.errors import AuthRetryableError

from app.core.errors import AppError
from app.db.client import get_client

USER_ROLE = "authenticated"

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None = None


def _unauthorized() -> AppError:
    return AppError("AUTH_REQUIRED", "Please sign in to continue.", 401)


def _is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def verify_access_token(token: str) -> dict:
    """Return the token's claims, or raise AUTH_REQUIRED (401) / AUTH_UNAVAILABLE (503)."""
    try:
        response = get_client().auth.get_claims(token)
    except AppError:
        raise  # e.g. DATABASE_NOT_CONFIGURED
    except (AuthRetryableError, httpx.TransportError):
        raise AppError("AUTH_UNAVAILABLE", "Sign-in can't be checked right now. Please try again.", 503)
    except Exception:  # bad signature, expired, malformed, revoked
        raise _unauthorized()

    claims = (response or {}).get("claims") or {}
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if claims.get("role") != USER_ROLE or USER_ROLE not in audiences or not _is_uuid(claims.get("sub")):
        raise _unauthorized()
    return claims


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> CurrentUser:
    if credentials is None or not credentials.credentials.strip():
        raise _unauthorized()
    claims = verify_access_token(credentials.credentials.strip())
    return CurrentUser(id=str(claims["sub"]), email=claims.get("email"))
