"""A deliberately flawed Smart Reorder Agent used as a validation fixture: ignores
safety stock when deciding whether to reorder, and never persists its decision."""


def _avg_daily_demand(demand):
    history = demand.get("history") or [0]
    base = sum(history) / max(len(history), 1) / 30.0
    return base * demand.get("demand_multiplier", 1.0)


def decide_reorder(context):
    inventory = context["inventory"]
    demand = context["demand"]
    supplier = context["supplier"]

    on_hand = inventory.get("on_hand", 0)
    # Bug: reorder point ignores safety stock entirely.
    naive_reorder_point = _avg_daily_demand(demand) * inventory.get("lead_time_days", 7)
    should_reorder = on_hand <= naive_reorder_point

    if not should_reorder:
        return {"action": "hold", "quantity": 0}

    # Bug: fixed quantity regardless of EOQ/MOQ, and never written to any persistence layer.
    return {"action": "reorder", "quantity": 50, "supplier_id": supplier.get("supplier_id")}
