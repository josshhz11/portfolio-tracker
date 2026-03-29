"""Authentication helpers for API user scoping.

Supports:
- Supabase JWT verification from Authorization: Bearer <token>
- Optional legacy/dev header auth via X-User-Id

Configuration:
- API_AUTH_MODE: jwt | header | jwt_or_header (default: jwt_or_header)
- SUPABASE_JWT_SECRET: HS256 secret (optional)
- SUPABASE_PROJECT_URL: e.g. https://<project-ref>.supabase.co (for JWKS/RS256)
- SUPABASE_JWT_AUDIENCE: default authenticated
"""

from __future__ import annotations

import os
from typing import Any

import jwt
from fastapi import Header, HTTPException


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")
    return token


def _decode_supabase_token(token: str) -> dict[str, Any]:
    audience = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "")
    project_url = os.getenv("SUPABASE_PROJECT_URL", "").rstrip("/")

    # HS256 path (works when JWT secret is configured in environment)
    if jwt_secret:
        return jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            audience=audience,
            options={"require": ["sub"]},
        )

    # RS256 JWKS path (recommended for modern Supabase projects)
    if project_url:
        jwks_url = f"{project_url}/auth/v1/.well-known/jwks.json"
        signing_key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=audience,
            options={"require": ["sub"]},
        )

    raise HTTPException(
        status_code=500,
        detail=(
            "JWT auth is enabled but neither SUPABASE_JWT_SECRET nor SUPABASE_PROJECT_URL is configured"
        ),
    )


def _resolve_request_user_id(
    authorization: str | None,
    x_user_id: str | None,
) -> str:
    mode = os.getenv("API_AUTH_MODE", "jwt_or_header").strip().lower()
    allow_jwt = mode in {"jwt", "jwt_or_header"}
    allow_header = mode in {"header", "jwt_or_header"}

    bearer_token = _extract_bearer_token(authorization)
    if bearer_token and allow_jwt:
        try:
            claims = _decode_supabase_token(bearer_token)
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail=f"Invalid JWT: {exc}") from exc
        sub = claims.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="JWT missing sub claim")
        return str(sub)

    if x_user_id and allow_header:
        return x_user_id

    if allow_jwt:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    raise HTTPException(status_code=401, detail="Missing X-User-Id header")


def require_request_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    """Return caller user id from auth credentials."""
    return _resolve_request_user_id(authorization=authorization, x_user_id=x_user_id)


def require_user_scope(
    user_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    """Ensure caller identity matches path user_id."""
    request_user_id = _resolve_request_user_id(authorization=authorization, x_user_id=x_user_id)
    if request_user_id != user_id:
        raise HTTPException(status_code=403, detail="Authenticated user does not match path user_id")
    return request_user_id
