from fastapi import APIRouter, Depends, HTTPException

from ..core import db
from ..core.auth import require_owner
from ..regression import engine as regression_engine

router = APIRouter(prefix="/api/history", tags=["history"])


def _owns_run(conn, run_id: str, owner_key: str) -> bool:
    row = conn.execute("SELECT 1 FROM runs WHERE run_id=? AND owner_key=?", (run_id, owner_key)).fetchone()
    return row is not None


@router.get("/compare/{run_id_a}/{run_id_b}")
def compare_runs(run_id_a: str, run_id_b: str, owner_key: str = Depends(require_owner)):
    with db.session() as conn:
        if not (_owns_run(conn, run_id_a, owner_key) and _owns_run(conn, run_id_b, owner_key)):
            raise HTTPException(404, "Run not found")
    try:
        report = regression_engine.compare(run_id_a, run_id_b)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return report.to_dict()


@router.get("/{subject_id}")
def get_history(subject_id: str, owner_key: str = Depends(require_owner)):
    with db.session() as conn:
        runs = [dict(r) for r in conn.execute(
            """SELECT run_id, status, overall_trust_score, production_readiness, created_at
               FROM runs WHERE subject_id=? AND owner_key=? AND status='completed' ORDER BY created_at ASC""",
            (subject_id, owner_key),
        )]
        deltas = [dict(r) for r in conn.execute(
            """SELECT historical_deltas.* FROM historical_deltas
               JOIN runs ON runs.run_id = historical_deltas.run_id
               WHERE historical_deltas.subject_id=? AND runs.owner_key=? ORDER BY historical_deltas.run_id""",
            (subject_id, owner_key),
        )]
    if not runs:
        raise HTTPException(404, "No completed runs found for this subject_id")
    for d in deltas:
        d["new_defects"] = db.load(d["new_defects"])
        d["resolved_defects"] = db.load(d["resolved_defects"])
        d["regressions"] = db.load(d["regressions"])
    return {"subject_id": subject_id, "runs": runs, "deltas": deltas}
