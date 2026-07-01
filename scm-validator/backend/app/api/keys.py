from datetime import datetime, timezone

from fastapi import APIRouter

from ..core import db
from ..core.auth import new_api_key

router = APIRouter(prefix="/api/keys", tags=["keys"])


@router.post("")
def create_key():
    """Self-service key issuance — no auth required to call this endpoint itself,
    since its whole purpose is to hand a first key to a brand-new client."""
    key = new_api_key()
    with db.session() as conn:
        conn.execute(
            "INSERT INTO api_keys (api_key, created_at) VALUES (?, ?)",
            (key, datetime.now(timezone.utc).isoformat()),
        )
    return {"api_key": key}
