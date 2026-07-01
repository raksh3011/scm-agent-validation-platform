"""Defect taxonomy referenced by defect_engine. Kept as plain data so new defect
types can be registered without touching the correlation logic's control flow."""

BUSINESS_DEFECTS = {
    "incorrect_reorder_decision", "wrong_reorder_quantity", "ignored_safety_stock",
    "ignored_lead_time", "ignored_inventory_position", "poor_replenishment_policy",
    "forecast_direction_error", "forecast_magnitude_error",
    "global_supplier_selection",  # NEW: supplier picked globally without product-SKU check
    "missing_supplier_filtering",  # NEW: no filtering of suppliers by product eligibility
}

OPERATIONAL_DEFECTS = {
    "missing_po_creation", "missing_persistence", "narrated_execution_only",
}

TECHNICAL_DEFECTS = {
    "runtime_instability", "entrypoint_unreachable", "exception_on_fault_injection",
}

ARCHITECTURAL_DEFECTS = {
    "tight_coupling_to_storage", "missing_separation_of_concerns",
}

DATA_QUALITY_DEFECTS = {
    "ignored_missing_master_data", "ignored_duplicate_records", "ignored_truncated_records",
}

SECURITY_DEFECTS = {
    "fails_on_adversarial_input", "trusts_unvalidated_input",
}

INTEGRATION_DEFECTS = {
    "erp_write_missing", "wms_write_missing",
}

RELIABILITY_DEFECTS = {
    "inconsistent_behaviour_across_categories", "non_reproducible_decision",
}

SCALABILITY_DEFECTS = {
    "fails_under_stress", "degrades_with_history_length",
}

PERFORMANCE_DEFECTS = {
    "slow_execution",
}

ALL_DEFECT_TYPES = (
    BUSINESS_DEFECTS | OPERATIONAL_DEFECTS | TECHNICAL_DEFECTS | ARCHITECTURAL_DEFECTS
    | DATA_QUALITY_DEFECTS | SECURITY_DEFECTS | INTEGRATION_DEFECTS | RELIABILITY_DEFECTS
    | SCALABILITY_DEFECTS | PERFORMANCE_DEFECTS
)
