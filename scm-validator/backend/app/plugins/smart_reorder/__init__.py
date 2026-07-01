"""Smart Reorder Agent plugin. Implementation is composed from the shared pipeline
stages rather than duplicated here:
  - classifier signature: detection.agent_classifier.TYPE_SIGNATURES["smart_reorder"]
  - scenario rule packs: rules/packs/inventory.yaml, demand.yaml, supplier.yaml,
    procurement.yaml, warehouse.yaml, runtime_faults.yaml (applies_to: smart_reorder)
  - business validator: validation.decision_validator.VALIDATORS["smart_reorder"]
  - reference math: validation.business_rules.reorder_math
"""
