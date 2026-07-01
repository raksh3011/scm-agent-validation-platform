"""Synthetic ERP data backing the sandbox. Deterministic (no randomness) so identical
repos always see identical baseline master data."""
import sqlite3
from pathlib import Path

SKUS = [
    {"sku": "SKU-1001", "name": "Industrial Bearing 6205", "unit_cost": 4.20, "lead_time_days": 7},
    {"sku": "SKU-1002", "name": "Hydraulic Hose 3/4in", "unit_cost": 11.50, "lead_time_days": 14},
    {"sku": "SKU-1003", "name": "Control Valve Assembly", "unit_cost": 86.00, "lead_time_days": 21},
    {"sku": "SKU-1004", "name": "Steel Bracket M8", "unit_cost": 1.10, "lead_time_days": 5},
    {"sku": "SKU-1005", "name": "PLC Module CPU-22", "unit_cost": 320.00, "lead_time_days": 35},
]

SUPPLIERS = [
    {"supplier_id": "SUP-A", "name": "Northbridge Components", "reliability_score": 0.95, "moq": 100, "capacity_per_week": 500},
    {"supplier_id": "SUP-B", "name": "Pacific Rim Parts", "reliability_score": 0.80, "moq": 50, "capacity_per_week": 1200},
    {"supplier_id": "SUP-C", "name": "Atlas Industrial Supply", "reliability_score": 0.60, "moq": 20, "capacity_per_week": 200},
]


def bootstrap(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS inventory (
            sku TEXT PRIMARY KEY, name TEXT, on_hand INTEGER, allocated INTEGER,
            on_order INTEGER, reserved INTEGER, safety_stock INTEGER, unit_cost REAL, lead_time_days INTEGER
        );
        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id TEXT PRIMARY KEY, name TEXT, reliability_score REAL, moq INTEGER, capacity_per_week INTEGER
        );
        CREATE TABLE IF NOT EXISTS demand_history (
            sku TEXT, period TEXT, quantity INTEGER
        );
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_id TEXT PRIMARY KEY, sku TEXT, supplier_id TEXT, quantity INTEGER, status TEXT, created_at TEXT
        );
    """)
    for s in SKUS:
        conn.execute(
            "INSERT OR IGNORE INTO inventory (sku, name, on_hand, allocated, on_order, reserved, safety_stock, "
            "unit_cost, lead_time_days) VALUES (?,?,?,?,?,?,?,?,?)",
            (s["sku"], s["name"], 200, 0, 0, 0, 40, s["unit_cost"], s["lead_time_days"]),
        )
    for sup in SUPPLIERS:
        conn.execute(
            "INSERT OR IGNORE INTO suppliers (supplier_id, name, reliability_score, moq, capacity_per_week) "
            "VALUES (?,?,?,?,?)",
            (sup["supplier_id"], sup["name"], sup["reliability_score"], sup["moq"], sup["capacity_per_week"]),
        )
    base_demand = [40, 42, 38, 45, 41, 39, 44, 43, 40, 46, 41, 39]
    for s in SKUS:
        for i, qty in enumerate(base_demand):
            conn.execute("INSERT INTO demand_history (sku, period, quantity) VALUES (?,?,?)",
                         (s["sku"], f"2025-{i+1:02d}", qty))
    conn.commit()
    conn.close()


def get_inventory_snapshot(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM inventory")]
    conn.close()
    return rows


def get_suppliers(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM suppliers")]
    conn.close()
    return rows


def get_demand_history(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM demand_history")]
    conn.close()
    return rows


def create_purchase_order(db_path: Path, supplier_id: str, sku: str, quantity: int) -> dict:
    import uuid
    from datetime import datetime, timezone
    conn = sqlite3.connect(db_path)
    po_id = uuid.uuid4().hex[:10]
    conn.execute("INSERT INTO purchase_orders (po_id, sku, supplier_id, quantity, status, created_at) "
                 "VALUES (?,?,?,?,?,?)",
                 (po_id, sku, supplier_id, quantity, "created", datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    return {"po_id": po_id, "sku": sku, "supplier_id": supplier_id, "quantity": quantity}
