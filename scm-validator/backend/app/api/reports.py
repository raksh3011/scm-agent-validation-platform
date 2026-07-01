from fastapi import APIRouter, Depends, HTTPException, Response

from ..core import db
from ..core.auth import require_owner

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{run_id}")
def get_report(run_id: str, owner_key: str = Depends(require_owner)):
    with db.session() as conn:
        row = conn.execute(
            """SELECT reports.pdf_data FROM reports
               JOIN runs ON runs.run_id = reports.run_id
               WHERE reports.run_id=? AND runs.owner_key=?""",
            (run_id, owner_key),
        ).fetchone()
    if not row or not row["pdf_data"]:
        raise HTTPException(404, "Report not found for this run")
    pdf_bytes = bytes(row["pdf_data"])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{run_id}_assurance_report.pdf"'},
    )
