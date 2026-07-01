import secrets

from fastapi import Header, HTTPException

from . import db


def new_api_key() -> str:
    return secrets.token_hex(20)


def require_owner(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
    """Every run/history endpoint is scoped to the caller's own API key so that
    one user's submissions and audit trail are never visible to another user.
    Call POST /api/keys once (no auth required) to obtain a key, then send it
    on every subsequent request via the X-API-Key header."""
    if not x_api_key:
        raise HTTPException(401, "Missing X-API-Key header. Call POST /api/keys to obtain one.")
    with db.session() as conn:
        row = conn.execute("SELECT api_key FROM api_keys WHERE api_key=?", (x_api_key,)).fetchone()
    if not row:
        raise HTTPException(401, "Invalid API key.")
    return x_api_key
