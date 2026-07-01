"""Central plugin registry. Each agent type contributes classifier signals (see
detection.agent_classifier.TYPE_SIGNATURES), scenario rule packs (see rules/packs),
and a business decision validator (see validation.decision_validator.VALIDATORS).
This module is the single place that declares which agent types have a *complete*
plugin (scenario generation + execution + business validation) versus which are
detectable but not yet fully supported — adding a new fully-supported type means
adding a rule pack + a validator function + an entry here, nothing else changes."""

FULLY_SUPPORTED_AGENT_TYPES = {"smart_reorder", "demand_forecasting"}

DETECTED_ONLY_AGENT_TYPES = {
    "supplier_selection", "procurement_agent", "warehouse_agent",
    "inventory_optimization", "transportation_agent", "production_planning",
    "manufacturing_agent",
}


def is_fully_supported(agent_type: str) -> bool:
    return agent_type in FULLY_SUPPORTED_AGENT_TYPES


def coverage_note(agent_type: str) -> str | None:
    if agent_type in DETECTED_ONLY_AGENT_TYPES:
        return (f"'{agent_type.replace('_', ' ')}' was detected but scenario coverage for this agent type "
                "is not yet available in this build. Classification and structural findings are still reported.")
    if agent_type in ("unknown", "unrecognized"):
        return "No SCM agent decision logic could be identified in this repository."
    return None
