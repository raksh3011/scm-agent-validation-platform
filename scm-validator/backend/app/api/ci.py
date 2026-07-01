"""Continuous-validation integration point. This is a stub webhook receiver plus a
documented GitHub Actions example — not a full GitHub/GitLab/Azure DevOps App. Point
any CI pipeline or scheduler at POST /api/runs/{subject_id}/rerun (see api/runs.py)
to trigger regression validation after a code change.

Example GitHub Actions step:

    - name: Trigger SCM agent assurance re-validation
      run: |
        curl -X POST "$ASSURANCE_API_URL/api/runs/${{ secrets.SUBJECT_ID }}/rerun"
"""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/ci", tags=["ci"])


@router.post("/webhook")
async def ci_webhook(request: Request):
    payload = await request.json()
    return {"received": True, "note": "Use POST /api/runs/{subject_id}/rerun to trigger re-validation.",
            "payload_keys": list(payload.keys())}
