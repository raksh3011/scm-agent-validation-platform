import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "validator.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    source_type TEXT NOT NULL,         -- repo_url | zip | files
    source_ref TEXT,                   -- url or path
    use_case TEXT,
    expected_io TEXT,
    description TEXT,
    enable_llm_insights INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'queued',
    overall_trust_score REAL,
    verdict TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS score_breakdown (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    dimension TEXT NOT NULL,
    score REAL NOT NULL,
    max_score REAL NOT NULL,
    remarks TEXT
);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    why_it_matters TEXT,
    score_impact REAL,
    evidence_refs TEXT  -- json list
);

CREATE TABLE IF NOT EXISTS recommendations (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    finding_id TEXT NOT NULL,
    title TEXT NOT NULL,
    recommendation TEXT,
    priority TEXT,
    expected_impact TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    file_path TEXT,
    line_start INTEGER DEFAULT 0,
    line_end INTEGER DEFAULT 0,
    snippet TEXT,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS ai_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    insight TEXT NOT NULL
);
"""


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def dump_refs(refs: list[str]) -> str:
    return json.dumps(refs)


def load_refs(raw: str | None) -> list[str]:
    if not raw:
        return []
    return json.loads(raw)
