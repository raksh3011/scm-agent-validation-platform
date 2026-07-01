"""Converts static architecture/maturity flags (maturity_analyzer) into Defect
records. Unlike defect_engine.correlate (which requires runtime scenario
evidence), these defects are backed by static evidence — file path + line —
because the underlying fact (no persistence call exists anywhere in the
source, no test files exist, weights are hardcoded literals) cannot be
observed by running scenarios; it has to be read from the code itself.

This exists because the dynamic scenario engine alone can score a thin,
non-production prototype highly if it merely doesn't crash on the generated
inputs. A hardcoded prediction table, simulated (non-persisted) actions, and
no retry/validation around an external API call are real production-readiness
defects that no amount of scenario passing will surface."""
import uuid

from ..core.models import Defect

# (defect_type) -> (category, severity, title, business_impact, technical_explanation_template,
#                    recommendation, verification_steps)
_CATALOG: dict[str, dict] = {
    "no_statistical_or_ml_forecasting_model": dict(
        category="data_quality", severity="critical",
        title="No statistical or ML model backs demand prediction",
        business_impact="Demand predictions cannot generalize to new products, seasons, or markets — every "
                         "input the agent has not been explicitly pre-programmed for is handled incorrectly.",
        recommendation="Replace the hardcoded/rule-based prediction with a trained forecasting model "
                        "(e.g. exponential smoothing, regression, or a properly validated LLM call) that "
                        "learns from historical demand rather than a fixed lookup.",
    ),
    "hardcoded_or_rule_based_predictions": dict(
        category="data_quality", severity="critical",
        title="Predictions are hardcoded or rule-based, not learned",
        business_impact="The agent cannot reason about products, contexts, or events it was not explicitly "
                         "coded for — it has no real generalization capability.",
        recommendation="Replace the fixed lookup table / keyword-match logic with a model that computes a "
                        "prediction from the actual historical data passed in.",
    ),
    "no_uncertainty_or_confidence_estimation": dict(
        category="data_quality", severity="critical",
        title="Predictions carry no uncertainty or confidence estimate",
        business_impact="Downstream consumers cannot distinguish a high-confidence forecast from a guess, "
                         "so risk-aware decisions (e.g. safety stock sizing) cannot be made correctly.",
        recommendation="Attach a confidence/uncertainty interval to every prediction and propagate it into "
                        "the safety-stock and reorder-point calculations.",
    ),
    "incomplete_scm_state_machine": dict(
        category="architectural", severity="critical",
        title="Agent does not implement a complete SCM state machine",
        business_impact="Without distinct observe/analyze/plan/execute/monitor/learn phases, the agent's "
                         "behavior cannot be audited, paused, or partially re-run at a meaningful boundary.",
        recommendation="Restructure the agent around explicit phases (Observe -> Analyze -> Plan -> Execute "
                        "-> Monitor -> Learn) with a clear, inspectable handoff between each.",
    ),
    "no_feedback_or_learning_loop": dict(
        category="architectural", severity="critical",
        title="No feedback or continuous learning loop",
        business_impact="The agent repeats the same mistakes indefinitely — forecast error, supplier "
                         "scoring drift, and outcome quality never improve from observed history.",
        recommendation="Persist actual outcomes (sales vs. forecast, on-time vs. promised delivery) and feed "
                        "them back into the prediction/scoring logic on a recurring cadence.",
    ),
    "no_continuous_monitoring": dict(
        category="architectural", severity="high",
        title="No continuous monitoring of decisions after execution",
        business_impact="A bad decision (wrong supplier, missed stockout) is never detected after the fact "
                         "because nothing tracks the outcome of a decision once it is made.",
        recommendation="Add a monitoring phase that periodically checks decision outcomes against expected "
                        "results and raises an alert on divergence.",
    ),
    "supplier_selection_ignores_product_context": dict(
        category="business", severity="critical",
        title="Supplier selection is product-agnostic",
        business_impact="The same 'best' supplier is recommended for every product regardless of which "
                         "suppliers actually carry it, its price for that specific SKU, or category fit.",
        recommendation="Filter the supplier candidate list to the specific product before scoring, and "
                        "score using that product's price/lead-time/reliability for that supplier.",
    ),
    "no_retry_or_error_handling_for_external_api_calls": dict(
        category="reliability", severity="critical",
        title="No retry or error handling around external API calls",
        business_impact="A transient network error or rate limit on the LLM/API call crashes the entire "
                         "decision run instead of degrading gracefully or retrying.",
        recommendation="Wrap external API calls in try/except with bounded retries and a documented "
                        "fallback (e.g. revert to the last-known-good prediction) on persistent failure.",
    ),
    "unvalidated_llm_output_parsing": dict(
        category="reliability", severity="critical",
        title="LLM output is parsed and trusted without validation",
        business_impact="A malformed, truncated, or adversarial LLM response can silently corrupt business "
                         "decisions or crash the agent — there is no schema check before the value is used.",
        recommendation="Validate the parsed response against an explicit schema (types, ranges) before "
                        "using it, and reject/retry on validation failure instead of trusting it blindly.",
    ),
    "no_real_persistence_simulated_actions_only": dict(
        category="operational", severity="critical",
        title="Actions are simulated; nothing is actually persisted",
        business_impact="Purchase orders, ERP status updates, and finance alerts only exist as console "
                         "output or in-memory objects — no downstream system ever sees them.",
        recommendation="Persist every action (purchase order, status update, alert) to a real database or "
                        "system of record, not just a printed/returned summary.",
    ),
    "missing_core_scm_entities": dict(
        category="architectural", severity="high",
        title="Missing core SCM entities (PO / Shipment / Receipt / Transaction)",
        business_impact="Without durable Purchase Order, Shipment, Receipt, and Transaction records, the "
                         "agent cannot support reconciliation, audit, or any downstream SCM process.",
        recommendation="Model and persist the missing entities explicitly, with foreign keys back to the "
                        "decision that created them.",
    ),
    "static_demand_context_no_realtime_integration": dict(
        category="integration", severity="high",
        title="Demand context is static; no real-time data integration",
        business_impact="The agent only ever reacts to a fixed, manually-edited text file — it cannot "
                         "respond to real demand signals, promotions, or events as they happen.",
        recommendation="Integrate a live data source (POS feed, promotions calendar, weather API) instead "
                        "of a static local context file.",
    ),
    "reorder_logic_ignores_moq": dict(
        category="business", severity="high",
        title="Reorder logic ignores supplier MOQ",
        business_impact="Orders sized purely from the reorder-point formula can fall below a supplier's "
                         "minimum order quantity, producing an order the supplier will reject or upcharge.",
        recommendation="Clamp every recommended order quantity to at least the selected supplier's MOQ.",
    ),
    "reorder_logic_ignores_capacity_constraints": dict(
        category="business", severity="high",
        title="Reorder logic ignores supplier/warehouse capacity",
        business_impact="A recommended order can exceed what the supplier can produce or the warehouse can "
                         "receive in the relevant period, creating a commitment the business cannot fulfill.",
        recommendation="Cap recommended quantities against supplier capacity-per-period and warehouse "
                        "receiving capacity before finalizing the order.",
    ),
    "hardcoded_business_weights": dict(
        category="architectural", severity="high",
        title="Supplier/business scoring weights are hardcoded",
        business_impact="Changing how price, reliability, or lead time are weighted requires a code change "
                         "and redeploy instead of a configuration update — the business cannot tune policy.",
        recommendation="Move scoring weights into configuration (env vars, a settings file, or a database "
                        "row) so they can be tuned without a code change.",
    ),
    "no_business_input_validation": dict(
        category="data_quality", severity="high",
        title="No validation of business inputs",
        business_impact="Negative stock, invalid supplier records, or other malformed business data flow "
                         "straight into the decision logic and produce a nonsensical or crashing decision.",
        recommendation="Validate every business input (non-negative quantities, valid supplier references, "
                        "bounded reliability scores) before it reaches the decision logic, and reject or "
                        "quarantine invalid records explicitly.",
    ),
    "no_structured_logging": dict(
        category="operational", severity="medium",
        title="No structured logging",
        business_impact="Operators cannot trace, filter, or alert on agent behavior in production — the "
                         "only signal is whatever happens to be printed to stdout.",
        recommendation="Adopt the standard `logging` module (or a structured logger) with levels and "
                        "machine-parseable fields instead of print statements.",
    ),
    "monolithic_single_file_architecture": dict(
        category="architectural", severity="medium",
        title="Monolithic single-file architecture",
        business_impact="Data access, business logic, scoring, and execution are tightly coupled in one or "
                         "two files, making the agent hard to test, extend, or partially replace.",
        recommendation="Split data access, business/decision logic, and action execution into separate "
                        "modules with clear interfaces between them.",
    ),
    "hardcoded_database_path": dict(
        category="architectural", severity="medium",
        title="Database path is hardcoded",
        business_impact="The agent cannot be deployed against a different database (staging, production, "
                         "per-tenant) without editing source code.",
        recommendation="Read the database connection string from configuration or an environment variable.",
    ),
    "no_automated_tests": dict(
        category="architectural", severity="medium",
        title="No automated tests in the submission",
        business_impact="Regressions in the reorder/forecast/scoring logic will not be caught before they "
                         "reach production — correctness depends entirely on this validator's external scenarios.",
        recommendation="Add unit tests for the decision/scoring functions and integration tests for the "
                        "end-to-end run, and wire them into CI.",
    ),
    "missing_ci_or_documentation": dict(
        category="architectural", severity="low",
        title="Missing CI pipeline or documentation",
        business_impact="Without CI, regressions ship undetected; without documentation, onboarding a new "
                         "maintainer or auditor to this agent is slow and error-prone.",
        recommendation="Add a CI workflow that runs tests on every change, and a README describing the "
                        "agent's purpose, inputs, outputs, and operating assumptions.",
    ),
}


def correlate(static_facts: dict) -> list[Defect]:
    maturity = static_facts.get("maturity") or {}
    defects: list[Defect] = []
    for defect_type, spec in _CATALOG.items():
        flagged = maturity.get(defect_type)
        if not flagged or not flagged.get("present"):
            continue
        occurrences = flagged.get("occurrences", [])
        first = occurrences[0] if occurrences else {}
        evidence_refs = [
            f"{o['file']}:{o['line']}" if o.get("file") and o.get("line") else (o.get("file") or "repository-wide")
            for o in occurrences
        ][:10]
        detail = first.get("detail", "")
        defects.append(Defect(
            id=uuid.uuid4().hex[:10],
            category=spec["category"],
            defect_type=defect_type,
            title=spec["title"],
            severity=spec["severity"],
            confidence=0.8 if first.get("file") else 0.65,
            business_impact=spec["business_impact"],
            technical_explanation=detail or spec["title"],
            recommendation=spec["recommendation"],
            verification_steps=(
                ["Open the cited file/line", "Confirm the absence/presence described matches the source"]
                if first.get("file") else
                ["Search the repository for the pattern described", "Confirm the absence described is repository-wide"]
            ),
            scenario_refs=[],
            evidence_refs=evidence_refs,
            file_path=first.get("file"),
            line_number=first.get("line"),
            function_name=first.get("function"),
            root_cause=detail or None,
        ))
    return defects
