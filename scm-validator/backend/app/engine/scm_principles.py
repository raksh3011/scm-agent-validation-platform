"""SCM Principle Validation Engine — the core trust layer for reorder agents.

This module encodes supply-chain management principles as executable checks.
It runs submitted agents through test scenarios and validates their decisions
against SCM logic rules.

This is NOT static analysis. This evaluates actual agent behavior.
"""
import subprocess
import json
import tempfile
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentDecision:
    """Normalized agent decision output."""
    action: str  # "REORDER" | "HOLD"
    qty: float
    supplier_id: Optional[str]
    rop: Optional[float]
    d_adj: Optional[float]  # adjusted demand
    on_hand: float
    error: Optional[str]
    raw_output: dict


@dataclass
class SCMScenario:
    """A test scenario for validating SCM principles."""
    id: str
    description: str
    product: dict
    suppliers: list[dict]
    context: str
    injected_multiplier: Optional[float] = None
    injected_supplier_id: Optional[str] = None
    expected_action: Optional[str] = None
    expected_rop_min: Optional[float] = None
    expected_rop_max: Optional[float] = None
    expected_qty_min: Optional[float] = None
    expected_qty_max: Optional[float] = None
    expected_supplier: Optional[str] = None


@dataclass
class PrincipleCheck:
    """Result of checking one SCM principle."""
    principle_id: str
    principle_name: str
    passed: bool
    severity: str  # "Required" | "Recommended"
    evidence: str
    scenario_id: Optional[str] = None


@dataclass
class InvariantCheck:
    """Result of checking a monotonicity or safety invariant."""
    invariant_id: str
    invariant_name: str
    passed: bool
    evidence: str


@dataclass
class SCMHarnessResult:
    """Complete result from SCM principle harness."""
    is_applicable: bool
    applicability_reason: str
    principle_checks: list[PrincipleCheck]
    invariant_checks: list[InvariantCheck]
    scenario_results: list[dict]
    scm_score: float
    blockers: list[str]


# ================ ADAPTER LAYER ================

def generate_adapter(workspace: Path) -> Optional[Path]:
    """Generate a standardized adapter for the submitted agent.
    
    The adapter normalizes different agent implementations to a common interface:
    
    def run_decision(scenario: dict) -> dict:
        returns {
            "action": "REORDER" | "HOLD",
            "qty": float,
            "supplier_id": str | None,
            "rop": float | None,
            "d_adj": float | None,
            "on_hand": float,
            "error": str | None
        }
    """
    # Look for main agent file
    agent_files = list(workspace.glob("**/*agent*.py")) + list(workspace.glob("**/*reorder*.py"))
    
    if not agent_files:
        return None
    
    main_agent = agent_files[0]
    
    # Generate adapter code
    adapter_code = f'''"""
Auto-generated adapter for SCM agent validation.
This adapter normalizes the agent's interface for principle testing.
"""
import sys
import json
import os
from pathlib import Path

# Add agent directory to path
agent_dir = Path({str(workspace.absolute())!r})
sys.path.insert(0, str(agent_dir))

def run_decision(scenario):
    """Run agent decision and return normalized output."""
    try:
        # Import the agent module
        import importlib.util
        spec = importlib.util.spec_from_file_location("agent_module", {str(main_agent.absolute())!r})
        agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent)
        
        # Setup scenario
        product = scenario["product"]
        suppliers = scenario["suppliers"]
        context = scenario.get("context", "")
        
        # Try to call the agent's decide function
        if hasattr(agent, "decide"):
            result = agent.decide(product, suppliers, context, live=False)
            
            return {{
                "action": result.get("action", "UNKNOWN"),
                "qty": result.get("qty", 0),
                "supplier_id": result.get("supplier", {{}}).get("supplier_id") if isinstance(result.get("supplier"), dict) else None,
                "rop": result.get("rop"),
                "d_adj": result.get("d_adj"),
                "on_hand": result.get("on_hand", product.get("on_hand_qty", 0)),
                "error": None
            }}
        else:
            return {{"error": "Agent has no 'decide' function"}}
            
    except Exception as e:
        return {{"error": f"Adapter execution failed: {{str(e)}}"}}

if __name__ == "__main__":
    scenario = json.loads(sys.argv[1])
    result = run_decision(scenario)
    print(json.dumps(result))
'''
    
    adapter_path = workspace / "_scm_adapter.py"
    adapter_path.write_text(adapter_code)
    return adapter_path


def run_agent_decision(adapter_path: Path, scenario: SCMScenario, timeout: int = 10) -> AgentDecision:
    """Execute agent through adapter in isolated subprocess."""
    scenario_dict = {
        "product": scenario.product,
        "suppliers": scenario.suppliers,
        "context": scenario.context,
    }
    
    try:
        result = subprocess.run(
            ["python", str(adapter_path), json.dumps(scenario_dict)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=adapter_path.parent,
        )
        
        if result.returncode != 0:
            return AgentDecision(
                action="ERROR",
                qty=0,
                supplier_id=None,
                rop=None,
                d_adj=None,
                on_hand=scenario.product.get("on_hand_qty", 0),
                error=f"Agent crashed: {result.stderr[:500]}",
                raw_output={}
            )
        
        output = json.loads(result.stdout.strip())
        
        if output.get("error"):
            return AgentDecision(
                action="ERROR",
                qty=0,
                supplier_id=None,
                rop=None,
                d_adj=None,
                on_hand=scenario.product.get("on_hand_qty", 0),
                error=output["error"],
                raw_output=output
            )
        
        return AgentDecision(
            action=output.get("action", "UNKNOWN"),
            qty=output.get("qty", 0),
            supplier_id=output.get("supplier_id"),
            rop=output.get("rop"),
            d_adj=output.get("d_adj"),
            on_hand=output.get("on_hand", scenario.product.get("on_hand_qty", 0)),
            error=None,
            raw_output=output
        )
        
    except subprocess.TimeoutExpired:
        return AgentDecision(
            action="ERROR",
            qty=0,
            supplier_id=None,
            rop=None,
            d_adj=None,
            on_hand=scenario.product.get("on_hand_qty", 0),
            error="Agent execution timed out",
            raw_output={}
        )
    except Exception as e:
        return AgentDecision(
            action="ERROR",
            qty=0,
            supplier_id=None,
            rop=None,
            d_adj=None,
            on_hand=scenario.product.get("on_hand_qty", 0),
            error=f"Harness error: {str(e)}",
            raw_output={}
        )


# ================ GOLDEN SCENARIOS ================

def get_golden_scenarios() -> list[SCMScenario]:
    """Return the set of required test scenarios for SCM reorder agents."""
    
    return [
        # GS-01: Basic ROP arithmetic check
        SCMScenario(
            id="GS-01",
            description="Basic ROP arithmetic: ROP = (d × mult × L) + SS",
            product={
                "product_id": "P1",
                "product_name": "Widget A",
                "on_hand_qty": 350,
                "safety_stock": 150,
                "avg_daily_sales": 50,
            },
            suppliers=[
                {"supplier_id": "S1", "unit_price": 1.00, "lead_time_days": 3, "reliability": 0.95, "products": ["P1"]},
            ],
            context="Normal demand, no special conditions.",
            injected_multiplier=1.5,
            expected_rop_min=375,  # (50 * 1.5 * 3) + 150 = 375
            expected_rop_max=375,
            expected_action="REORDER",  # on_hand 350 <= ROP 375
        ),
        
        # GS-02: Boundary condition - exactly at ROP should reorder
        SCMScenario(
            id="GS-02",
            description="Boundary: on_hand == ROP must REORDER",
            product={
                "product_id": "P1",
                "product_name": "Widget A",
                "on_hand_qty": 375,  # Exactly at ROP
                "safety_stock": 150,
                "avg_daily_sales": 50,
            },
            suppliers=[
                {"supplier_id": "S1", "unit_price": 1.00, "lead_time_days": 3, "reliability": 0.95, "products": ["P1"]},
            ],
            context="Normal demand.",
            injected_multiplier=1.5,
            expected_action="REORDER",
        ),
        
        # GS-03: One above ROP should HOLD
        SCMScenario(
            id="GS-03",
            description="Boundary: on_hand = ROP + 1 must HOLD",
            product={
                "product_id": "P1",
                "product_name": "Widget A",
                "on_hand_qty": 376,  # One above ROP
                "safety_stock": 150,
                "avg_daily_sales": 50,
            },
            suppliers=[
                {"supplier_id": "S1", "unit_price": 1.00, "lead_time_days": 3, "reliability": 0.95, "products": ["P1"]},
            ],
            context="Normal demand.",
            injected_multiplier=1.5,
            expected_action="HOLD",
        ),
        
        # GS-04: Negative qty is never valid
        SCMScenario(
            id="GS-04",
            description="Safety: order qty must never be negative",
            product={
                "product_id": "P1",
                "product_name": "Widget A",
                "on_hand_qty": 1000,  # Well above ROP
                "safety_stock": 150,
                "avg_daily_sales": 50,
            },
            suppliers=[
                {"supplier_id": "S1", "unit_price": 1.00, "lead_time_days": 3, "reliability": 0.95, "products": ["P1"]},
            ],
            context="Normal demand.",
            injected_multiplier=1.0,
            expected_action="HOLD",
            expected_qty_min=0,
        ),
        
        # GS-05: Zero suppliers should fail safely
        SCMScenario(
            id="GS-05",
            description="Safety: agent must handle zero suppliers gracefully",
            product={
                "product_id": "P1",
                "product_name": "Widget A",
                "on_hand_qty": 100,
                "safety_stock": 150,
                "avg_daily_sales": 50,
            },
            suppliers=[],  # No suppliers!
            context="Normal demand.",
            injected_multiplier=1.0,
            expected_action="ERROR",  # Should fail safely, not crash
        ),
        
        # GS-06: Multi-factor supplier selection
        SCMScenario(
            id="GS-06",
            description="Supplier selection: not price-only, consider reliability/lead time",
            product={
                "product_id": "P1",
                "product_name": "Widget A",
                "on_hand_qty": 100,
                "safety_stock": 150,
                "avg_daily_sales": 50,
            },
            suppliers=[
                {"supplier_id": "S1", "unit_price": 0.80, "lead_time_days": 12, "reliability": 0.70, "products": ["P1"]},  # Cheapest but worst
                {"supplier_id": "S2", "unit_price": 1.00, "lead_time_days": 3, "reliability": 0.95, "products": ["P1"]},   # Balanced best
            ],
            context="Normal demand.",
            injected_multiplier=1.0,
            expected_supplier="S2",  # Should NOT pick cheapest alone
        ),
        
        # GS-07: THE CRITICAL ONE - Supplier-product eligibility
        SCMScenario(
            id="GS-07",
            description="CRITICAL: Supplier must actually carry the product (SKU eligibility)",
            product={
                "product_id": "P2",  # Different product!
                "product_name": "Widget B",
                "on_hand_qty": 100,
                "safety_stock": 150,
                "avg_daily_sales": 50,
            },
            suppliers=[
                {"supplier_id": "S1", "unit_price": 0.90, "lead_time_days": 3, "reliability": 0.95, "products": ["P1"]},      # Does NOT carry P2!
                {"supplier_id": "S2", "unit_price": 1.10, "lead_time_days": 5, "reliability": 0.90, "products": ["P1", "P2"]},  # Carries P2
            ],
            context="Normal demand.",
            injected_multiplier=1.5,
            expected_supplier="S2",  # MUST pick S2, not S1 (even though S1 is cheaper/faster)
        ),
        
        # GS-08: Determinism check
        SCMScenario(
            id="GS-08",
            description="Determinism: same input twice in mock mode must yield identical output",
            product={
                "product_id": "P1",
                "product_name": "Widget A",
                "on_hand_qty": 350,
                "safety_stock": 150,
                "avg_daily_sales": 50,
            },
            suppliers=[
                {"supplier_id": "S1", "unit_price": 1.00, "lead_time_days": 3, "reliability": 0.95, "products": ["P1"]},
            ],
            context="Normal demand.",
            injected_multiplier=1.0,
            # Will be run twice, outputs must match exactly
        ),
    ]


# ================ INVARIANT CHECKS ================

def check_rop_monotonicity_lead_time(adapter_path: Path) -> InvariantCheck:
    """ROP must increase as lead time increases (all else equal)."""
    base_scenario = SCMScenario(
        id="INV-01",
        description="ROP monotonicity: lead time",
        product={
            "product_id": "P1",
            "on_hand_qty": 500,
            "safety_stock": 150,
            "avg_daily_sales": 50,
        },
        suppliers=[
            {"supplier_id": "S1", "unit_price": 1.00, "lead_time_days": 3, "reliability": 0.95, "products": ["P1"]},
        ],
        context="",
        injected_multiplier=1.0,
    )
    
    # Run with L=3
    decision_1 = run_agent_decision(adapter_path, base_scenario)
    
    # Run with L=7
    base_scenario.suppliers[0]["lead_time_days"] = 7
    decision_2 = run_agent_decision(adapter_path, base_scenario)
    
    if decision_1.error or decision_2.error:
        return InvariantCheck(
            invariant_id="INV-01",
            invariant_name="ROP monotonicity: lead time",
            passed=False,
            evidence=f"Agent failed: {decision_1.error or decision_2.error}"
        )
    
    if decision_1.rop is None or decision_2.rop is None:
        return InvariantCheck(
            invariant_id="INV-01",
            invariant_name="ROP monotonicity: lead time",
            passed=False,
            evidence="Agent did not return ROP value"
        )
    
    passed = decision_2.rop > decision_1.rop
    
    return InvariantCheck(
        invariant_id="INV-01",
        invariant_name="ROP must increase as lead time increases",
        passed=passed,
        evidence=f"L=3 → ROP={decision_1.rop:.1f}, L=7 → ROP={decision_2.rop:.1f} (must increase)"
    )


def check_rop_monotonicity_safety_stock(adapter_path: Path) -> InvariantCheck:
    """ROP must increase as safety stock increases (all else equal)."""
    base_scenario = SCMScenario(
        id="INV-02",
        description="ROP monotonicity: safety stock",
        product={
            "product_id": "P1",
            "on_hand_qty": 500,
            "safety_stock": 100,
            "avg_daily_sales": 50,
        },
        suppliers=[
            {"supplier_id": "S1", "unit_price": 1.00, "lead_time_days": 3, "reliability": 0.95, "products": ["P1"]},
        ],
        context="",
        injected_multiplier=1.0,
    )
    
    decision_1 = run_agent_decision(adapter_path, base_scenario)
    
    base_scenario.product["safety_stock"] = 200
    decision_2 = run_agent_decision(adapter_path, base_scenario)
    
    if decision_1.error or decision_2.error:
        return InvariantCheck(
            invariant_id="INV-02",
            invariant_name="ROP monotonicity: safety stock",
            passed=False,
            evidence=f"Agent failed: {decision_1.error or decision_2.error}"
        )
    
    if decision_1.rop is None or decision_2.rop is None:
        return InvariantCheck(
            invariant_id="INV-02",
            invariant_name="ROP monotonicity: safety stock",
            passed=False,
            evidence="Agent did not return ROP value"
        )
    
    passed = decision_2.rop > decision_1.rop
    
    return InvariantCheck(
        invariant_id="INV-02",
        invariant_name="ROP must increase as safety stock increases",
        passed=passed,
        evidence=f"SS=100 → ROP={decision_1.rop:.1f}, SS=200 → ROP={decision_2.rop:.1f} (must increase)"
    )


def check_no_negative_qty(adapter_path: Path) -> InvariantCheck:
    """Order quantity must never be negative."""
    scenarios = get_golden_scenarios()
    
    for scenario in scenarios:
        decision = run_agent_decision(adapter_path, scenario)
        
        if decision.error:
            continue
        
        if decision.qty < 0:
            return InvariantCheck(
                invariant_id="INV-03",
                invariant_name="Order quantity must never be negative",
                passed=False,
                evidence=f"Scenario {scenario.id}: qty={decision.qty} < 0"
            )
    
    return InvariantCheck(
        invariant_id="INV-03",
        invariant_name="Order quantity must never be negative",
        passed=True,
        evidence="All scenarios produced qty >= 0"
    )


def check_determinism(adapter_path: Path) -> InvariantCheck:
    """Running same scenario twice must produce identical output."""
    scenario = [s for s in get_golden_scenarios() if s.id == "GS-08"][0]
    
    decision_1 = run_agent_decision(adapter_path, scenario)
    decision_2 = run_agent_decision(adapter_path, scenario)
    
    if decision_1.error or decision_2.error:
        return InvariantCheck(
            invariant_id="INV-04",
            invariant_name="Determinism in mock mode",
            passed=False,
            evidence="Agent execution failed"
        )
    
    # Compare key fields
    same_action = decision_1.action == decision_2.action
    same_qty = abs(decision_1.qty - decision_2.qty) < 0.01
    same_supplier = decision_1.supplier_id == decision_2.supplier_id
    
    passed = same_action and same_qty and same_supplier
    
    return InvariantCheck(
        invariant_id="INV-04",
        invariant_name="Deterministic output for same input",
        passed=passed,
        evidence=f"Run 1: {decision_1.action}, qty={decision_1.qty:.1f}, supplier={decision_1.supplier_id} | "
                f"Run 2: {decision_2.action}, qty={decision_2.qty:.1f}, supplier={decision_2.supplier_id} | "
                f"Match: {passed}"
    )


def run_invariant_checks(adapter_path: Path) -> list[InvariantCheck]:
    """Run all invariant checks."""
    return [
        check_rop_monotonicity_lead_time(adapter_path),
        check_rop_monotonicity_safety_stock(adapter_path),
        check_no_negative_qty(adapter_path),
        check_determinism(adapter_path),
    ]


# ================ PRINCIPLE VALIDATION ================

def validate_principles(adapter_path: Path) -> tuple[list[PrincipleCheck], list[dict]]:
    """Run golden scenarios and validate SCM principles."""
    scenarios = get_golden_scenarios()
    principle_checks = []
    scenario_results = []
    
    for scenario in scenarios:
        decision = run_agent_decision(adapter_path, scenario)
        
        result = {
            "scenario_id": scenario.id,
            "description": scenario.description,
            "decision": decision.raw_output,
            "passed": True,
            "failures": []
        }
        
        # Check expected ROP
        if scenario.expected_rop_min is not None and decision.rop is not None:
            if not (scenario.expected_rop_min <= decision.rop <= scenario.expected_rop_max):
                result["passed"] = False
                result["failures"].append(f"ROP={decision.rop:.1f}, expected {scenario.expected_rop_min}-{scenario.expected_rop_max}")
                
                principle_checks.append(PrincipleCheck(
                    principle_id=f"P-ROP-{scenario.id}",
                    principle_name="ROP formula correctness",
                    passed=False,
                    severity="Required",
                    evidence=f"{scenario.id}: ROP={decision.rop:.1f}, expected {scenario.expected_rop_min}",
                    scenario_id=scenario.id
                ))
        
        # Check expected action
        if scenario.expected_action and decision.action != scenario.expected_action:
            if not (scenario.expected_action == "ERROR" and decision.error):
                result["passed"] = False
                result["failures"].append(f"action={decision.action}, expected {scenario.expected_action}")
                
                principle_checks.append(PrincipleCheck(
                    principle_id=f"P-ACTION-{scenario.id}",
                    principle_name="Correct reorder decision",
                    passed=False,
                    severity="Required",
                    evidence=f"{scenario.id}: action={decision.action}, expected {scenario.expected_action}",
                    scenario_id=scenario.id
                ))
        
        # Check expected supplier (CRITICAL for GS-07)
        if scenario.expected_supplier and decision.supplier_id != scenario.expected_supplier:
            result["passed"] = False
            result["failures"].append(f"supplier={decision.supplier_id}, expected {scenario.expected_supplier}")
            
            severity = "Required" if scenario.id == "GS-07" else "Recommended"
            
            principle_checks.append(PrincipleCheck(
                principle_id=f"P-SUPPLIER-{scenario.id}",
                principle_name="Supplier eligibility (product-SKU match)" if scenario.id == "GS-07" else "Supplier selection",
                passed=False,
                severity=severity,
                evidence=f"{scenario.id}: selected {decision.supplier_id}, expected {scenario.expected_supplier}",
                scenario_id=scenario.id
            ))
        
        # Check qty bounds
        if scenario.expected_qty_min is not None:
            if decision.qty < scenario.expected_qty_min:
                result["passed"] = False
                result["failures"].append(f"qty={decision.qty}, below minimum {scenario.expected_qty_min}")
                
                principle_checks.append(PrincipleCheck(
                    principle_id=f"P-QTY-{scenario.id}",
                    principle_name="Order quantity bounds",
                    passed=False,
                    severity="Required",
                    evidence=f"{scenario.id}: qty={decision.qty}, violates minimum {scenario.expected_qty_min}",
                    scenario_id=scenario.id
                ))
        
        scenario_results.append(result)
    
    return principle_checks, scenario_results


# ================ MAIN HARNESS ================

def run_scm_harness(workspace: Path) -> SCMHarnessResult:
    """Run complete SCM principle harness on submitted agent."""
    
    # Check applicability (is this even a reorder agent?)
    agent_files = list(workspace.glob("**/*agent*.py")) + list(workspace.glob("**/*reorder*.py"))
    
    if not agent_files:
        return SCMHarnessResult(
            is_applicable=False,
            applicability_reason="No agent files found (no *agent*.py or *reorder*.py files)",
            principle_checks=[],
            invariant_checks=[],
            scenario_results=[],
            scm_score=0,
            blockers=["Not a reorder agent"]
        )
    
    # Generate adapter
    adapter_path = generate_adapter(workspace)
    
    if not adapter_path:
        return SCMHarnessResult(
            is_applicable=False,
            applicability_reason="Could not generate adapter for agent",
            principle_checks=[],
            invariant_checks=[],
            scenario_results=[],
            scm_score=0,
            blockers=["Adapter generation failed"]
        )
    
    try:
        # Run invariant checks
        invariant_checks = run_invariant_checks(adapter_path)
        
        # Run principle validation (golden scenarios)
        principle_checks, scenario_results = validate_principles(adapter_path)
        
        # Compute SCM score
        scm_score = compute_scm_score(principle_checks, invariant_checks, scenario_results)
        
        # Identify blockers
        blockers = []
        for check in principle_checks:
            if not check.passed and check.severity == "Required":
                blockers.append(f"{check.principle_name}: {check.evidence}")
        
        for inv in invariant_checks:
            if not inv.passed:
                blockers.append(f"{inv.invariant_name}: {inv.evidence}")
        
        return SCMHarnessResult(
            is_applicable=True,
            applicability_reason="Reorder agent detected and validated",
            principle_checks=principle_checks,
            invariant_checks=invariant_checks,
            scenario_results=scenario_results,
            scm_score=scm_score,
            blockers=blockers
        )
    
    finally:
        # Cleanup adapter
        if adapter_path and adapter_path.exists():
            adapter_path.unlink()


def compute_scm_score(
    principle_checks: list[PrincipleCheck],
    invariant_checks: list[InvariantCheck],
    scenario_results: list[dict]
) -> float:
    """Compute SCM Logic Quality score from harness results.
    
    This is the source of truth for SCM score, NOT static regex patterns.
    """
    score = 100.0
    
    # Invariant failures are severe
    for inv in invariant_checks:
        if not inv.passed:
            score -= 20
    
    # Required principle failures are critical
    for check in principle_checks:
        if not check.passed:
            if check.severity == "Required":
                score -= 15
            else:
                score -= 5
    
    # Scenario pass rate
    if scenario_results:
        passed_count = sum(1 for r in scenario_results if r["passed"])
        scenario_penalty = (1 - passed_count / len(scenario_results)) * 30
        score -= scenario_penalty
    
    return max(0.0, score)

