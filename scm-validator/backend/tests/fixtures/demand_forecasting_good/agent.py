"""A reasonably correct Demand Forecasting Agent used as a validation fixture."""


def _moving_average(history, window=3):
    if not history:
        return 0.0
    vals = history[-window:]
    return sum(vals) / len(vals)


def forecast_demand(context):
    demand = context["demand"]
    history = demand.get("history") or [0]
    multiplier = demand.get("demand_multiplier", 1.0)

    baseline = _moving_average(history)
    trend = (history[-1] - history[0]) / max(len(history), 1) if len(history) > 1 else 0.0

    forecast = (baseline + trend) * multiplier
    return {"forecast": round(forecast, 1), "baseline": round(baseline, 1), "method": "moving_average_with_trend"}
