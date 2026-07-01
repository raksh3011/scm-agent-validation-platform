"""Independent reference SCM math for inventory/reorder decisions — computed from the
same scenario inputs the agent sees, so the agent's decision can be judged against a
textbook-correct answer rather than against itself."""
import math


def inventory_position(inventory: dict) -> float:
    return (inventory.get("on_hand", 0) + inventory.get("on_order", 0)
            - inventory.get("allocated", 0) - inventory.get("reserved", 0))


def avg_daily_demand(demand: dict) -> float:
    history = demand.get("history") or [0]
    base = sum(history) / max(len(history), 1) / 30.0
    return base * demand.get("demand_multiplier", 1.0)


def reorder_point(inventory: dict, demand: dict) -> float:
    lead_time = inventory.get("lead_time_days", 7)
    return avg_daily_demand(demand) * lead_time + inventory.get("safety_stock", 0)


def should_reorder(inventory: dict, demand: dict) -> bool:
    return inventory_position(inventory) <= reorder_point(inventory, demand)


def eoq(annual_demand: float, order_cost: float = 50.0, holding_cost_per_unit: float = 2.0) -> float:
    if annual_demand <= 0 or holding_cost_per_unit <= 0:
        return 0.0
    return math.sqrt((2 * annual_demand * order_cost) / holding_cost_per_unit)


def reference_order_quantity(inventory: dict, demand: dict, supplier: dict) -> float:
    annual_demand = avg_daily_demand(demand) * 365
    qty = eoq(annual_demand, holding_cost_per_unit=max(inventory.get("unit_cost", 1.0) * 0.2, 0.5))
    moq = supplier.get("moq", 0)
    return max(qty, moq)
