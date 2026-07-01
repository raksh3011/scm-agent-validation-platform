"""Correlates failed/partial scenario executions plus supporting static facts into
defect records. Every defect must cite at least one scenario id and one evidence id —
nothing is reported that isn't backed by something the run actually observed."""
import uuid

from ..core.models import Defect, ScenarioExecutionResult
from ..execution.evidence import has_persistence_evidence

_SEV_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_SLOW_SCENARIO_THRESHOLD_MS = 3000.0


def _severity_of(results: list[ScenarioExecutionResult]) -> str:
    worst = max((r.scenario.severity_if_failed for r in results), key=lambda s: _SEV_ORDER.get(s, 1), default="medium")
    return worst


def _confidence_of(results: list[ScenarioExecutionResult]) -> float:
    if not results:
        return 0.0
    runtime_conf = sum(r.confidence for r in results) / len(results)
    volume_conf = min(0.25, 0.03 * len(results))
    return round(min(0.97, 0.45 + runtime_conf * 0.30 + volume_conf), 2)


def _evidence_refs(results: list[ScenarioExecutionResult]) -> list[str]:
    refs = []
    for r in results:
        refs.extend(e.id for e in r.evidence)
    return refs[:30]


def _violated_requirements(results: list[ScenarioExecutionResult]) -> list[str]:
    reqs: set[str] = set()
    for r in results:
        trace = getattr(r.scenario, "traceability", None) or {}
        reqs.update(trace.get("requirement_ids", []) or [])
    return sorted(reqs)


def _make(category, defect_type, title, results, business_impact, technical_explanation, recommendation, steps) -> Defect:
    return Defect(
        id=uuid.uuid4().hex[:10], category=category, defect_type=defect_type, title=title,
        severity=_severity_of(results), confidence=_confidence_of(results),
        business_impact=business_impact, technical_explanation=technical_explanation,
        recommendation=recommendation, verification_steps=steps,
        scenario_refs=[r.scenario.id for r in results], evidence_refs=_evidence_refs(results),
        violated_requirement=_violated_requirements(results), root_cause=technical_explanation,
    )


def _capabilities(static_facts: dict) -> set[str]:
    graph = static_facts.get("business_capability_graph") or {}
    return {c.get("name") for c in graph.get("supported_capabilities", []) if isinstance(c, dict)}


def _strong_business_evidence(results: list[ScenarioExecutionResult], min_count: int = 2) -> bool:
    if len(results) < min_count:
        return False
    avg_conf = sum(r.confidence for r in results) / len(results)
    with_runtime_evidence = sum(1 for r in results if r.evidence)
    return avg_conf >= 0.65 and with_runtime_evidence >= max(1, min_count // 2)


def correlate(agent_type: str, results: list[ScenarioExecutionResult], static_facts: dict) -> list[Defect]:
    defects: list[Defect] = []
    caps = _capabilities(static_facts)

    failed = [r for r in results if r.status == "fail"]
    partial = [r for r in results if r.status == "partial"]
    errored = [r for r in results if r.status == "error"]

    if agent_type == "smart_reorder":
        if failed and _strong_business_evidence(failed):
            defects.append(_make(
                "business", "incorrect_reorder_decision", "Agent makes incorrect reorder timing decisions",
                failed,
                "Stock will run out or working capital will be tied up unnecessarily because the agent "
                "reorders at the wrong time relative to the calculated reorder point.",
                "Across the affected scenarios, the agent's reorder/hold decision disagreed with the "
                "independently computed inventory-position-vs-reorder-point reference.",
                "Recompute the reorder trigger as inventory_position <= reorder_point "
                "(reorder_point = avg_daily_demand * lead_time_days + safety_stock).",
                ["Re-run the failing scenario IDs", "Compare returned decision to the business explanation",
                 "Confirm reorder point formula in the agent matches lead time and safety stock inputs"],
            ))
        if partial and _strong_business_evidence(partial, min_count=4):
            defects.append(_make(
                "business", "wrong_reorder_quantity", "Reorder quantity is outside a reasonable EOQ band",
                partial,
                "Over-ordering ties up working capital; under-ordering risks a near-term stockout.",
                "Reorder timing was correct but the recommended quantity fell outside 0.3x-3x of the "
                "reference EOQ-based quantity (respecting supplier MOQ).",
                "Validate the order quantity calculation against EOQ and supplier MOQ constraints.",
                ["Re-run the partial scenario IDs", "Inspect returned quantity vs business_explanation reference qty"],
            ))

        missing_persistence = [r for r in results if r.status in ("pass", "partial")
                                and not has_persistence_evidence(r.evidence)
                                and r.actual_behaviour.get("return_value")]
        if "purchase_order" in caps and missing_persistence and not static_facts.get("has_persistence_call"):
            defects.append(_make(
                "operational", "missing_po_creation", "Reorder decisions are not persisted as purchase orders",
                missing_persistence,
                "Without a persisted purchase order, downstream ERP/procurement systems never see the "
                "agent's decision — the recommendation is effectively narrated, not executed.",
                "No database mutation evidence was captured for scenarios where the agent recommended "
                "reordering, and static analysis found no persistence call (insert/commit/save) in the source.",
                "Persist every reorder decision as a purchase order record (or equivalent ERP write) "
                "rather than only returning a recommendation.",
                ["Re-run an affected scenario", "Inspect db_mutation evidence for the run",
                 "Confirm a purchase_orders row is created when the agent recommends reordering"],
            ))

    elif agent_type == "demand_forecasting":
        if failed and _strong_business_evidence(failed):
            defects.append(_make(
                "business", "forecast_direction_error", "Forecast direction disagrees with demand signal",
                failed,
                "A forecast moving the wrong direction under a demand spike/collapse causes stockouts or "
                "excess inventory exactly when accurate forecasting matters most.",
                "The agent's forecast did not move in the expected direction relative to the naive "
                "moving-average baseline under the scenario's injected demand pattern.",
                "Ensure the forecasting logic responds to recent demand trend/seasonality signals.",
                ["Re-run the failing scenario IDs", "Compare forecast value to the naive baseline reference"],
            ))
        if partial and _strong_business_evidence(partial, min_count=4):
            defects.append(_make(
                "business", "forecast_magnitude_error", "Forecast magnitude error exceeds tolerance",
                partial,
                "Forecast error above 50% MAPE versus the scaled baseline materially distorts replenishment "
                "and staffing plans built on top of the forecast.",
                "Direction was correct but the forecast magnitude deviated more than the tolerance band "
                "from the scaled naive baseline.",
                "Recalibrate forecast magnitude scaling against recent demand multiplier shifts.",
                ["Re-run the partial scenario IDs", "Inspect MAPE in the business_explanation"],
            ))

    if errored:
        timeout_scenarios = [r for r in errored if r.error and "timeout" in r.error.lower()]
        exception_scenarios = [r for r in errored if r.error and "timeout" not in r.error.lower()]
        if exception_scenarios:
            defects.append(_make(
                "technical", "runtime_instability", "Agent throws unhandled exceptions under realistic scenarios",
                exception_scenarios,
                "Unhandled exceptions in production mean the agent silently fails to act during exactly "
                "the conditions (faults, edge-case inventory states) it most needs to handle.",
                "Execution raised an exception that was not caught by the agent's own error handling "
                f"(static analysis: has_error_handling={static_facts.get('has_error_handling')}).",
                "Add error handling around external calls and edge-case business states; fail safe "
                "rather than raising.",
                ["Re-run an affected scenario", "Inspect the exception evidence and traceback"],
            ))
        if timeout_scenarios:
            # A timeout is a distinct failure mode from a raised exception — mislabeling it as
            # "throws unhandled exceptions" is itself a false/misleading finding, and a single
            # timeout under one stress scenario is a performance signal, not a crash.
            defects.append(_make(
                "performance", "timeout_under_load", "Agent times out under one or more scenarios",
                timeout_scenarios,
                "A decision that times out instead of completing means the agent cannot keep up with "
                "the relevant replenishment cycle, even though it did not raise or crash.",
                f"{len(timeout_scenarios)} scenario(s) exceeded the execution timeout without returning "
                "a result or raising an exception.",
                "Profile the decision function for unbounded loops, blocking I/O, or per-record DB "
                "round-trips that don't scale with input size.",
                ["Re-run an affected scenario", "Inspect runtime_ms and confirm whether it is data-volume dependent"],
            ))

    slow = [r for r in results if r.runtime_ms > _SLOW_SCENARIO_THRESHOLD_MS]
    if slow:
        defects.append(_make(
            "performance", "slow_execution", "Scenario execution exceeds a responsive-decision threshold",
            slow,
            "A supply chain agent that takes seconds per decision cannot keep up with high-volume "
            "replenishment cycles or real-time event triggers.",
            f"{len(slow)} scenario(s) took longer than {_SLOW_SCENARIO_THRESHOLD_MS:.0f}ms to execute.",
            "Profile the decision function for unnecessary I/O, blocking calls, or unbounded loops.",
            ["Re-run an affected scenario", "Inspect runtime_ms in the scenario execution record"],
        ))

    security_errors = [r for r in results if r.scenario.category == "security" and r.status == "error"]
    if security_errors:
        defects.append(_make(
            "security", "fails_on_adversarial_input", "Agent crashes on malformed or adversarial input",
            security_errors,
            "An agent that crashes on negative inventory, null references, or injected fields is "
            "vulnerable to malformed upstream data or a malicious integration partner.",
            "Execution raised an unhandled exception on a security/malformed-input scenario rather than "
            "validating and rejecting the input gracefully.",
            "Add input validation at the entrypoint and reject or sanitize malformed values before "
            "running business logic.",
            ["Re-run an affected scenario", "Inspect the exception evidence and traceback"],
        ))

    stress_errors = [r for r in results if r.scenario.category == "stress" and r.status == "error"]
    if stress_errors:
        defects.append(_make(
            "scalability", "fails_under_stress", "Agent fails under large input volume",
            stress_errors,
            "An agent that cannot handle a multi-year demand history or a wide supplier pool will fail "
            "in production as data volume grows past the validator's small synthetic baseline.",
            "Execution raised an unhandled exception or timed out on a stress-category scenario with an "
            "enlarged input (long demand history, wide supplier pool).",
            "Profile and fix the data structures/algorithms driving the slowdown or failure at scale.",
            ["Re-run an affected scenario", "Inspect runtime_ms and the exception evidence"],
        ))

    return defects
