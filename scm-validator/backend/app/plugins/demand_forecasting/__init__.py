"""Demand Forecasting Agent plugin. Implementation is composed from the shared
pipeline stages rather than duplicated here:
  - classifier signature: detection.agent_classifier.TYPE_SIGNATURES["demand_forecasting"]
  - scenario rule packs: rules/packs/demand.yaml (demand_pattern + data_quality axes),
    runtime_faults.yaml (applies_to: demand_forecasting)
  - business validator: validation.decision_validator.VALIDATORS["demand_forecasting"]
  - reference math: validation.business_rules.forecast_baseline
"""
