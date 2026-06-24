import sqlite3
import importlib.util
import math


def load_agent(path):
    spec = importlib.util.spec_from_file_location("agent", path)
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)
    return agent


SCENARIOS = [
    {
        "product_id": "P1",
        "actual_daily_sales": 120,
        "context": """
Heavy rainfall and localized flooding are expected.
Bottled water demand has increased by 18%.
Several stores report faster-than-normal inventory depletion.
"""
    },
    {
        "product_id": "P2",
        "actual_daily_sales": 95,
        "context": """
Normal weather conditions.
Demand remains stable.
No significant seasonal event.
"""
    },
    {
        "product_id": "P3",
        "actual_daily_sales": 75,
        "context": """
Heatwave plus holiday weekend.
Sports drink demand is elevated.
Customers purchasing more hydration products.
"""
    }
]


def forecast_metrics(results):
    mae = sum(abs(r["forecast"] - r["actual"]) for r in results) / len(results)

    mape = (
        sum(
            abs(r["forecast"] - r["actual"]) /
            max(r["actual"], 1)
            for r in results
        ) / len(results)
    ) * 100

    rmse = math.sqrt(
        sum(
            (r["forecast"] - r["actual"]) ** 2
            for r in results
        ) / len(results)
    )

    return mae, mape, rmse


def validate(agent):
    con = sqlite3.connect(agent.DB)

    products, suppliers, _ = agent.perceive(con)

    con.close()

    product_map = {
        p["product_id"]: p
        for p in products
    }

    results = []

    for scenario in SCENARIOS:

        product = dict(
            product_map[scenario["product_id"]]
        )

        actual = scenario["actual_daily_sales"]

        context = scenario["context"]

        mult, reason = agent.predict_demand(
            product,
            context,
            False
        )

        forecast = (
            product["avg_daily_sales"]
            * mult
        )

        decision = agent.decide(
            product,
            suppliers,
            context,
            False
        )

        predicted_reorder = (
            decision["action"] == "REORDER"
        )

        supplier = decision["supplier"]

        lead_time = supplier["lead_time_days"]

        safety_stock = product["safety_stock"]

        actual_rop = (
            actual * lead_time
            + safety_stock
        )

        truth_reorder = (
            product["on_hand_qty"]
            <= actual_rop
        )

        target = (
            actual *
            (
                lead_time +
                agent.REVIEW_PERIOD_DAYS
            )
            + safety_stock
        )

        ideal_qty = max(
            0,
            round(
                target -
                product["on_hand_qty"]
            )
        )

        results.append({
            "product_id":
                product["product_id"],

            "forecast":
                forecast,

            "actual":
                actual,

            "predicted_reorder":
                predicted_reorder,

            "truth_reorder":
                truth_reorder,

            "qty":
                decision["qty"],

            "ideal_qty":
                ideal_qty,

            "order_error":
                abs(
                    decision["qty"]
                    - ideal_qty
                ),

            "reason":
                reason
        })

    mae, mape, rmse = forecast_metrics(results)

    reorder_accuracy = (
        sum(
            1
            for r in results
            if r["predicted_reorder"]
            == r["truth_reorder"]
        )
        / len(results)
    )

    avg_order_error = (
        sum(
            r["order_error"]
            for r in results
        )
        / len(results)
    )

    trust_score = (
        (100 - min(mape, 100))
        * 0.4
        +
        reorder_accuracy
        * 100
        * 0.4
        +
        max(
            0,
            100 -
            avg_order_error / 10
        )
        * 0.2
    )

    print("\n========== VALIDATION REPORT ==========\n")

    print(
        f"MAE: {mae:.2f}"
    )

    print(
        f"MAPE: {mape:.2f}%"
    )

    print(
        f"RMSE: {rmse:.2f}"
    )

    print(
        f"Reorder Accuracy: "
        f"{reorder_accuracy:.2%}"
    )

    print(
        f"Average Order Error: "
        f"{avg_order_error:.2f}"
    )

    print(
        f"\nTrust Score: "
        f"{trust_score:.2f}/100"
    )

    print(
        "\nScenario Details:"
    )

    for r in results:

        print(
            f"\n{r['product_id']}"
        )

        print(
            f" Forecast: "
            f"{r['forecast']:.1f}"
        )

        print(
            f" Actual: "
            f"{r['actual']:.1f}"
        )

        print(
            f" Predicted Reorder: "
            f"{r['predicted_reorder']}"
        )

        print(
            f" Truth Reorder: "
            f"{r['truth_reorder']}"
        )

        print(
            f" Order Error: "
            f"{r['order_error']}"
        )

        print(
            f" Reason: "
            f"{r['reason']}"
        )


if __name__ == "__main__":

    agent = load_agent(
        "smart_reorder_agent.py"
    )

    validate(agent)