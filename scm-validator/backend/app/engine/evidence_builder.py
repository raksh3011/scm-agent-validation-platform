"""Converts raw finding evidence dicts into stable Evidence records and wires evidence_refs by id."""
import hashlib

from .rule_engine_v2 import RawFinding
from ..report_schema import Evidence


def _evidence_id(run_id: str, idx: int) -> str:
    return f"ev_{hashlib.sha1(f'{run_id}:{idx}'.encode()).hexdigest()[:10]}"


def build_evidence(run_id: str, findings: list[RawFinding]) -> tuple[list[Evidence], list[list[str]]]:
    """Returns (evidence_list, refs_per_finding) where refs_per_finding[i] are the evidence
    ids belonging to findings[i]. Index-aligned because multiple findings can share a rule_id
    (e.g. several hardcoded-secret hits), so rule_id alone isn't a unique key."""
    evidence_list: list[Evidence] = []
    refs_per_finding: list[list[str]] = []
    idx = 0
    for finding in findings:
        ids_for_finding = []
        for ev in finding.evidence:
            ev_id = _evidence_id(run_id, idx)
            idx += 1
            evidence_list.append(Evidence(
                id=ev_id,
                file_path=ev.get("file_path", ""),
                line_start=ev.get("line_start", 0) or 0,
                line_end=ev.get("line_end", 0) or 0,
                snippet=ev.get("snippet", ""),
                reason=ev.get("reason", ""),
            ))
            ids_for_finding.append(ev_id)
        refs_per_finding.append(ids_for_finding)
    return evidence_list, refs_per_finding
