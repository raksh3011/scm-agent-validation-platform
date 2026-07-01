"""Synthetic WMS data backing the sandbox."""
import sqlite3
from pathlib import Path

WAREHOUSES = [
    {"warehouse_id": "WH-EAST", "name": "East Distribution Center", "capacity_units": 50000, "available_units": 38000},
    {"warehouse_id": "WH-WEST", "name": "West Distribution Center", "capacity_units": 30000, "available_units": 5000},
]


def bootstrap(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS warehouses (
            warehouse_id TEXT PRIMARY KEY, name TEXT, capacity_units INTEGER, available_units INTEGER
        );
    """)
    for w in WAREHOUSES:
        conn.execute(
            "INSERT OR IGNORE INTO warehouses (warehouse_id, name, capacity_units, available_units) VALUES (?,?,?,?)",
            (w["warehouse_id"], w["name"], w["capacity_units"], w["available_units"]),
        )
    conn.commit()
    conn.close()


def get_warehouses(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM warehouses")]
    conn.close()
    return rows


def get_storage_constraints(db_path: Path, warehouse_id: str) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM warehouses WHERE warehouse_id=?", (warehouse_id,)).fetchone()
    conn.close()
    return dict(row) if row else {}
