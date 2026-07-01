import json
import os
import sqlite3
from contextlib import contextmanager

from .config import DB_PATH

# Free hosting tiers (Render, etc.) give the web service an ephemeral filesystem —
# a plain SQLite file would get wiped on every restart/redeploy, which defeats the
# purpose of a "history" feature. Set DATABASE_URL (e.g. a free Neon/Supabase
# Postgres) in the deployment environment and this module switches to Postgres,
# which is durable across restarts on a free plan. Local dev with no DATABASE_URL
# keeps using a SQLite file under storage/ — no Postgres account needed to hack
# on this locally.
DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras

SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects (
    subject_id TEXT PRIMARY KEY,
    label TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    api_key TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    owner_key TEXT,
    agent_name TEXT,
    source_type TEXT,
    source_ref TEXT,
    use_case TEXT,
    description TEXT,
    status TEXT NOT NULL,
    error TEXT,
    applicable INTEGER DEFAULT 1,
    not_applicable_reason TEXT,
    primary_agent_type TEXT,
    classification_confidence REAL,
    secondary_capabilities TEXT,
    suite_hash TEXT,
    overall_trust_score REAL,
    production_readiness TEXT,
    progress TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenarios (
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    name TEXT,
    category TEXT,
    business_objective TEXT,
    inputs TEXT,
    initial_state TEXT,
    expected_behaviour TEXT,
    severity_if_failed TEXT,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS scenario_executions (
    run_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    status TEXT NOT NULL,
    execution_state TEXT NOT NULL DEFAULT 'executed',
    actual_behaviour TEXT,
    business_explanation TEXT,
    confidence REAL,
    runtime_ms REAL,
    error TEXT,
    PRIMARY KEY (run_id, scenario_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    scenario_id TEXT,
    evidence_type TEXT NOT NULL,
    detail TEXT,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS defects (
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    category TEXT NOT NULL,
    defect_type TEXT NOT NULL,
    title TEXT,
    severity TEXT,
    confidence REAL,
    business_impact TEXT,
    technical_explanation TEXT,
    recommendation TEXT,
    verification_steps TEXT,
    scenario_refs TEXT,
    evidence_refs TEXT,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS trust_scores (
    run_id TEXT NOT NULL,
    dimension TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'uncategorized',
    score REAL,
    max_score REAL,
    rationale TEXT,
    state TEXT NOT NULL DEFAULT 'computed',
    reason TEXT,
    evidence_refs TEXT,
    PRIMARY KEY (run_id, dimension)
);

CREATE TABLE IF NOT EXISTS pipeline_stages (
    run_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    recovery_suggestions TEXT,
    duration_ms REAL,
    stage_order INTEGER NOT NULL,
    PRIMARY KEY (run_id, stage)
);

CREATE TABLE IF NOT EXISTS root_causes (
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    exception_type TEXT,
    normalized_message TEXT,
    confidence REAL,
    recovery_suggestion TEXT,
    affected_scenario_ids TEXT,
    affected_count INTEGER,
    representative_traceback TEXT,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS historical_deltas (
    run_id TEXT NOT NULL,
    previous_run_id TEXT,
    subject_id TEXT NOT NULL,
    score_delta REAL,
    new_defects TEXT,
    resolved_defects TEXT,
    regressions TEXT,
    PRIMARY KEY (run_id)
);

CREATE TABLE IF NOT EXISTS reports (
    run_id TEXT PRIMARY KEY,
    pdf_path TEXT,
    generated_at TEXT
);

CREATE TABLE IF NOT EXISTS kpi_results (
    run_id TEXT NOT NULL,
    name TEXT NOT NULL,
    value REAL,
    unit TEXT,
    description TEXT,
    PRIMARY KEY (run_id, name)
);

CREATE TABLE IF NOT EXISTS decision_traces (
    run_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    steps TEXT NOT NULL,
    PRIMARY KEY (run_id, scenario_id)
);

CREATE TABLE IF NOT EXISTS capability_graphs (
    run_id TEXT PRIMARY KEY,
    graph TEXT
);

CREATE TABLE IF NOT EXISTS agent_specifications (
    run_id TEXT PRIMARY KEY,
    spec TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_conformance (
    run_id TEXT NOT NULL,
    requirement_id TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL,
    rationale TEXT,
    repository_evidence TEXT,
    scenario_refs TEXT,
    evidence_refs TEXT,
    PRIMARY KEY (run_id, requirement_id)
);

CREATE TABLE IF NOT EXISTS conformance_summary (
    run_id TEXT PRIMARY KEY,
    conformance_score REAL,
    requirement_coverage REAL,
    functional_coverage REAL,
    input_coverage REAL,
    output_coverage REAL,
    constraint_coverage REAL,
    integration_coverage REAL,
    kpi_coverage REAL,
    decision_coverage REAL
);

CREATE TABLE IF NOT EXISTS evalgen_stats (
    run_id TEXT PRIMARY KEY,
    pairwise_coverage REAL,
    parameter_coverage REAL,
    interaction_coverage REAL,
    constraint_coverage REAL,
    redundant_scenario_reduction REAL,
    total_candidate_scenarios INTEGER,
    optimized_scenario_count INTEGER,
    parameters TEXT
);

"""


class _PGConnWrapper:
    """Makes a psycopg2 connection look like the sqlite3.Connection API this
    codebase's ~110 call sites already use: conn.execute(sql, params) returning
    a cursor with .fetchone()/.fetchall()/iteration, and dict-like rows via
    row["column"]. Keeps every existing query (all written with '?' params and
    dict(row) row access) unchanged — only this module knows which DB it's on."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql.replace("?", "%s"), params)
        return cur

    def executescript(self, script):
        cur = self._conn.cursor()
        cur.execute(script)
        cur.close()

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_conn():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        return _PGConnWrapper(conn)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def session():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


_MIGRATIONS = {
    "scenario_executions": [("execution_state", "TEXT NOT NULL DEFAULT 'executed'")],
    "trust_scores": [
        ("category", "TEXT NOT NULL DEFAULT 'uncategorized'"),
        ("state", "TEXT NOT NULL DEFAULT 'computed'"),
        ("reason", "TEXT"),
    ],
    "runs": [("progress", "TEXT"), ("owner_key", "TEXT")],
    "scenarios": [("traceability", "TEXT")],
    "defects": [("file_path", "TEXT"), ("function_name", "TEXT"), ("violated_requirement", "TEXT"),
                ("root_cause", "TEXT"), ("line_number", "INTEGER"), ("governance_refs", "TEXT")],
    # Generated PDFs also live in this table as bytes (BYTEA/BLOB), not just a
    # filesystem path — on a free host the local disk is wiped on every restart,
    # but the DB (Postgres, when DATABASE_URL is set) survives, so the report
    # stays downloadable regardless of what happened to the container's disk.
    "reports": [("pdf_data", "BYTEA" if USE_POSTGRES else "BLOB")],
}


def _migrate_existing_tables_sqlite(conn):
    for table, columns in _MIGRATIONS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, coldef in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {coldef}")


def _migrate_existing_tables_postgres(conn):
    for table, columns in _MIGRATIONS.items():
        for name, coldef in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {coldef}")


def init_db():
    with session() as conn:
        conn.executescript(SCHEMA)
        if USE_POSTGRES:
            _migrate_existing_tables_postgres(conn)
        else:
            _migrate_existing_tables_sqlite(conn)


def dump(obj) -> str:
    return json.dumps(obj, default=str)


def load(raw: str | None):
    if not raw:
        return None
    return json.loads(raw)
