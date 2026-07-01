from __future__ import annotations

import json
import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

import yaml

from .models import AgentSpecification, AsdRequirement

SECTION_ALIASES = {
    "business context": "business_context",
    "functional behaviour": "functional_behaviour",
    "functional behavior": "functional_behaviour",
    "inputs": "inputs",
    "outputs": "outputs",
    "integrations": "integrations",
    "constraints": "constraints",
    "kpis": "kpis",
    "scope": "scope",
    "out of scope": "out_of_scope",
    "stakeholders": "stakeholders",
    "decision policies": "decision_policies",
    "supported workflows": "workflows",
}

FIELD_TERMS = {
    "inputs": ["inventory", "demand", "lead time", "supplier", "forecast", "safety stock", "moq", "constraint"],
    "outputs": ["reorder", "purchase order", "supplier selection", "recommendation", "alert"],
    "integrations": ["erp", "wms", "oms", "procurement", "database", "api"],
    "kpis": ["service level", "fill rate", "stockout", "inventory turns", "working capital", "procurement cost"],
    "decision_policies": ["reorder point", "eoq", "min-max", "days of supply", "forecast", "periodic", "vmi"],
}


def _docx_text(raw: bytes) -> str:
    with zipfile.ZipFile(BytesIO(raw)) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for p in root.findall(".//w:p", ns):
        texts = [t.text or "" for t in p.findall(".//w:t", ns)]
        if texts:
            paragraphs.append("".join(texts))
    return "\n".join(paragraphs)


def _pdf_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _plain_text(raw: bytes) -> str:
    return raw.decode("utf-8", "ignore")


def _items_from_text(text: str) -> dict[str, list[str]]:
    current = "business_context"
    sections: dict[str, list[str]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip(" \t\r\n#*-•")
        if not line:
            continue
        key = SECTION_ALIASES.get(line.lower().rstrip(":"))
        if key:
            current = key
            continue
        sections.setdefault(current, []).append(line)
    return sections


def _extract_named_value(lines: list[str], labels: tuple[str, ...]) -> str | None:
    for line in lines:
        for label in labels:
            m = re.match(rf"{re.escape(label)}\s*[:\-]\s*(.+)$", line, re.I)
            if m:
                return m.group(1).strip()
    return None


def _keyword_hits(text: str) -> list[str]:
    lower = text.lower()
    hits = []
    for terms in FIELD_TERMS.values():
        for term in terms:
            if term in lower:
                hits.append(term.replace(" ", "_"))
    return sorted(set(hits))


def _requirements(sections: dict[str, list[str]]) -> list[AsdRequirement]:
    reqs: list[AsdRequirement] = []
    counter = 1
    for section, lines in sections.items():
        for line in lines:
            if len(line) < 4:
                continue
            required = not any(w in line.lower() for w in ("optional", "may ", "nice to have"))
            reqs.append(AsdRequirement(
                id=f"RQ-{counter:03d}",
                category=section,
                text=line,
                required=required,
                source_section=section,
                keywords=_keyword_hits(line),
            ))
            counter += 1
    return reqs


def _from_structured(source_name: str, fmt: str, data: dict, raw_text: str) -> AgentSpecification:
    spec = AgentSpecification(source_name=source_name, format=fmt, raw_text=raw_text)
    spec.agent_name = data.get("agent_name") or data.get("name")
    spec.scm_domain = data.get("scm_domain") or data.get("domain")
    spec.business_objective = data.get("business_objective") or data.get("objective")
    for attr in ("scope", "out_of_scope", "stakeholders", "responsibilities", "workflows",
                 "decision_policies", "inputs", "outputs", "integrations", "constraints", "kpis"):
        value = data.get(attr) or []
        setattr(spec, attr, value if isinstance(value, list) else [str(value)])
    spec.requirements = [
        AsdRequirement(id=r.get("id", f"RQ-{i:03d}"), category=r.get("category", "requirement"),
                       text=r.get("text", str(r)), required=r.get("required", True),
                       keywords=_keyword_hits(r.get("text", str(r))))
        for i, r in enumerate(data.get("requirements", []), start=1) if isinstance(r, dict)
    ]
    if not spec.requirements:
        spec.requirements = _requirements(_items_from_text(raw_text))
    return spec


def parse_asd_bytes(filename: str, raw: bytes) -> AgentSpecification:
    name = filename or "agent_specification"
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else "txt"
    if suffix == "docx":
        text, fmt = _docx_text(raw), "docx"
    elif suffix == "pdf":
        text, fmt = _pdf_text(raw), "pdf"
    elif suffix in ("yaml", "yml"):
        text, fmt = _plain_text(raw), "yaml"
        return _from_structured(name, fmt, yaml.safe_load(text) or {}, text)
    elif suffix == "json":
        text, fmt = _plain_text(raw), "json"
        return _from_structured(name, fmt, json.loads(text or "{}"), text)
    else:
        text, fmt = _plain_text(raw), "markdown" if suffix == "md" else suffix

    sections = _items_from_text(text)
    context = sections.get("business_context", [])
    spec = AgentSpecification(source_name=name, format=fmt, raw_text=text)
    spec.agent_name = _extract_named_value(context, ("agent name", "name"))
    spec.scm_domain = _extract_named_value(context, ("scm domain", "domain"))
    spec.business_objective = _extract_named_value(context, ("business objective", "objective"))
    spec.scope = sections.get("scope", [])
    spec.out_of_scope = sections.get("out_of_scope", [])
    spec.stakeholders = sections.get("stakeholders", [])
    spec.responsibilities = sections.get("functional_behaviour", [])
    spec.workflows = sections.get("workflows", [])
    spec.decision_policies = sections.get("decision_policies", [])
    spec.inputs = sections.get("inputs", []) or [t for t in FIELD_TERMS["inputs"] if t in text.lower()]
    spec.outputs = sections.get("outputs", []) or [t for t in FIELD_TERMS["outputs"] if t in text.lower()]
    spec.integrations = sections.get("integrations", []) or [t.upper() for t in FIELD_TERMS["integrations"] if t in text.lower()]
    spec.constraints = sections.get("constraints", [])
    spec.kpis = sections.get("kpis", []) or [t for t in FIELD_TERMS["kpis"] if t in text.lower()]
    spec.requirements = _requirements(sections)
    return spec
