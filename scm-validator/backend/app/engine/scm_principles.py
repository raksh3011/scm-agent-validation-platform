"""SCM-specific validation rules that detect supply chain logic violations.

These rules look for patterns that violate fundamental SCM principles:
- Product-supplier eligibility (a supplier must carry the product)
- ROP calculation correctness (must include lead time and safety stock)
- Demand forecasting isolation
- Supplier selection logic
"""
from dataclasses import dataclass
import ast
import re


@dataclass
class SCMViolation:
    rule_id: str
    severity: str  # "Critical", "High", "Medium", "Low"
    title: str
    description: str
    why_it_matters: str
    score_impact: float
    file_path: str
    line_start: int = 0


def check_global_supplier_selection(facts: dict) -> list[SCMViolation]:
    """Detect if supplier is selected globally without product-specific filtering.
    
    DEFECT PATTERN:
        supplier = choose_supplier(all_suppliers)  # Wrong!
        for product in products:
            use that same supplier for this product  # Ignores product-SKU eligibility
            
    CORRECT PATTERN:
        for product in products:
            eligible_suppliers = filter_suppliers_for_product(product, suppliers)
            supplier = choose_supplier(eligible_suppliers)
    """
    violations = []
    
    for fpath, content in facts["code_files"].items():
        if not fpath.endswith(".py"):
            continue
            
        lines = content.split("\n")
        
        # Look for supplier selection happening outside product loop
        # Pattern: supplier selection followed by product loop using that supplier
        for i, line in enumerate(lines):
            # Check for supplier selection patterns
            if re.search(r'supplier\s*[,=].*choose.*supplier', line, re.IGNORECASE):
                # Check if this is inside a function
                func_indent = _get_indent_level(line)
                
                # Look ahead to see if there's a product loop that uses this supplier
                for j in range(i+1, min(i+30, len(lines))):
                    next_line = lines[j]
                    # Check for product iteration
                    if re.search(r'for\s+\w+\s+in\s+(products|product_list)', next_line, re.IGNORECASE):
                        # Check if the supplier variable is used in this loop
                        loop_indent = _get_indent_level(next_line)
                        for k in range(j+1, min(j+20, len(lines))):
                            loop_body = lines[k]
                            if _get_indent_level(loop_body) <= loop_indent and loop_body.strip():
                                break  # End of loop
                            # Check if supplier is used without re-selection
                            if 'supplier' in loop_body.lower() and 'choose' not in loop_body.lower() and 'filter' not in loop_body.lower():
                                violations.append(SCMViolation(
                                    rule_id="SCM_GLOBAL_SUPPLIER",
                                    severity="Critical",
                                    title="Global Supplier Selection Ignores Product-SKU Eligibility",
                                    description=(
                                        f"Supplier is selected once at line {i+1} and reused for all products. "
                                        f"This violates the fundamental SCM principle that a supplier must carry "
                                        f"the specific product/SKU being ordered. The code selects a supplier globally "
                                        f"(possibly based on price or lead time) but never checks if that supplier "
                                        f"actually stocks each product in the product loop starting at line {j+1}."
                                    ),
                                    why_it_matters=(
                                        "This will cause the agent to create purchase orders for products that the "
                                        "selected supplier doesn't carry. In production, this leads to rejected orders, "
                                        "stockouts, manual firefighting, and potential business relationship damage. "
                                        "The Reverbend test agent fails GS-07 (supplier-SKU eligibility) for exactly this reason."
                                    ),
                                    score_impact=40.0,
                                    file_path=fpath,
                                    line_start=i+1
                                ))
                                break
                        break
    
    return violations


def check_rop_without_lead_time(facts: dict) -> list[SCMViolation]:
    """Detect ROP calculations that don't include lead time.
    
    DEFECT PATTERN:
        rop = demand + safety_stock  # Missing lead time!
        
    CORRECT PATTERN:
        rop = demand * lead_time + safety_stock
    """
    violations = []
    
    for fpath, content in facts["code_files"].items():
        if not fpath.endswith(".py"):
            continue
            
        lines = content.split("\n")
        
        for i, line in enumerate(lines):
            # Look for ROP calculation
            if re.search(r'rop\s*=', line, re.IGNORECASE):
                # Check if lead_time or L is in the calculation
                # Look at the next few lines in case it's multi-line
                calculation_block = "\n".join(lines[i:min(i+3, len(lines))])
                
                has_lead_time = bool(re.search(r'(lead_time|lead|L\s*[*)])', calculation_block, re.IGNORECASE))
                has_demand = bool(re.search(r'(demand|daily_sales|d_adj|d\')', calculation_block, re.IGNORECASE))
                
                if has_demand and not has_lead_time:
                    violations.append(SCMViolation(
                        rule_id="SCM_ROP_NO_LEAD_TIME",
                        severity="High",
                        title="ROP Calculation Missing Lead Time",
                        description=(
                            f"Reorder Point calculation at line {i+1} includes demand but doesn't multiply "
                            f"by lead time. ROP must account for the stock consumed during the supplier's "
                            f"lead time: ROP = (demand_per_day × lead_time_days) + safety_stock."
                        ),
                        why_it_matters=(
                            "Without lead time in ROP, the agent will reorder too late, causing stockouts. "
                            "Lead time is critical: if a supplier takes 10 days to deliver, you need enough "
                            "stock to cover those 10 days plus safety buffer."
                        ),
                        score_impact=25.0,
                        file_path=fpath,
                        line_start=i+1
                    ))
    
    return violations


def _get_indent_level(line: str) -> int:
    """Return the indentation level (number of leading spaces/tabs)."""
    return len(line) - len(line.lstrip())


def run_scm_rules(facts: dict, context: dict) -> list[SCMViolation]:
    """Run all SCM-specific rules and return violations."""
    violations = []
    
    violations.extend(check_global_supplier_selection(facts))
    violations.extend(check_rop_without_lead_time(facts))
    
    return violations
