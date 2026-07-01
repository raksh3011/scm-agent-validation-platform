"""A reasonably correct Smart Reorder Agent used as a validation fixture."""
import math
import sqlite3
import uuid
from datetime import datetime, timezone


def _avg_daily_demand(demand):
    history = demand.get("history") or [0]
    base = sum(history) / max(len(history), 1) / 30.0
    return base * demand.get("demand_multiplier", 1.0)


def _inventory_position(inventory):
    return (inventory.get("on_hand", 0) + inventory.get("on_order", 0)
            - inventory.get("allocated", 0) - inventory.get("reserved", 0))


def _reorder_point(inventory, demand):
    return _avg_daily_demand(demand) * inventory.get("lead_time_days", 7) + inventory.get("safety_stock", 0)


def _eoq(annual_demand, order_cost=50.0, holding_cost=2.0):
    if annual_demand <= 0:
        return 0.0
    return math.sqrt((2 * annual_demand * order_cost) / holding_cost)


def decide_reorder(context):
    inventory = context["inventory"]
    demand = context["demand"]
    supplier = context["supplier"]

    ip = _inventory_position(inventory)
    rp = _reorder_point(inventory, demand)
    should_reorder = ip <= rp

    if not should_reorder:
        return {"action": "hold", "quantity": 0, "supplier_id": None}

    annual_demand = _avg_daily_demand(demand) * 365
    qty = max(_eoq(annual_demand, holding_cost=max(inventory.get("unit_cost", 1.0) * 0.2, 0.5)),
              supplier.get("moq", 0))

    db_path = context.get("db_path")
    if db_path:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO purchase_orders (po_id, sku, supplier_id, quantity, status, created_at) VALUES (?,?,?,?,?,?)",
            (uuid.uuid4().hex[:10], context.get("sku"), supplier.get("supplier_id"), int(qty), "created",
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

    return {"action": "reorder", "quantity": int(qty), "supplier_id": supplier.get("supplier_id")}
