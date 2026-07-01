from ..core.models import Evidence


def summarize(evidence_list: list[Evidence]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in evidence_list:
        counts[e.evidence_type] = counts.get(e.evidence_type, 0) + 1
    return counts


def has_persistence_evidence(evidence_list: list[Evidence]) -> bool:
    return any(e.evidence_type == "db_mutation" for e in evidence_list)


def has_exception(evidence_list: list[Evidence]) -> bool:
    return any(e.evidence_type == "exception" for e in evidence_list)
