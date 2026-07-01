"""Naive reference forecast + error metrics used to judge a forecasting agent's
directional and magnitude reasonableness (there is no single 'correct' forecast, so
validation is tolerance-banded rather than exact-match)."""


def moving_average(history: list[float], window: int = 3) -> float:
    if not history:
        return 0.0
    window_vals = history[-window:]
    return sum(window_vals) / len(window_vals)


def naive_baseline_forecast(demand: dict) -> float:
    history = demand.get("history") or [0]
    return moving_average(history)


def expected_direction(demand: dict) -> str:
    multiplier = demand.get("demand_multiplier", 1.0)
    if multiplier >= 1.3:
        return "increase"
    if multiplier <= 0.7:
        return "decrease"
    return "stable"


def bias(actual: float, forecast: float) -> float:
    if actual == 0:
        return 0.0
    return (forecast - actual) / actual


def mape(actual: float, forecast: float) -> float:
    if actual == 0:
        return 0.0
    return abs((actual - forecast) / actual)
