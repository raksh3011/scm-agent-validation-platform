"""Optional, additive-only insight layer.

This module NEVER computes or influences the official trust score or findings.
It receives only the already-computed structured evidence (not raw repo content)
and returns plain-language commentary strings. If disabled, misconfigured, or
the call fails, the pipeline simply proceeds with an empty ai_insights list --
this must never block or fail a validation run.
"""
import json
import os

from ..report_schema import Finding, ScoreBreakdownItem


def generate_insights(
    agent_name: str,
    use_case: str | None,
    breakdown: list[ScoreBreakdownItem],
    findings: list[Finding],
) -> list[str]:
    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("LLM_INSIGHTS_ENDPOINT"):
        return []

    compact_context = {
        "agent_name": agent_name,
        "use_case": use_case or "not declared",
        "score_breakdown": [{"dimension": b.dimension, "score": b.score} for b in breakdown],
        "top_findings": [
            {"severity": f.severity, "category": f.category, "title": f.title}
            for f in sorted(findings, key=lambda x: x.score_impact, reverse=True)[:8]
        ],
    }

    prompt = (
        "You are a supply-chain trust advisor. Given this structured, already-scored "
        "validation summary (do NOT change or restate any score), produce up to 5 short "
        "bullet-point insights about business-logic risk, missing assumptions, or customer-facing "
        "trust commentary. Return strict JSON: {\"insights\": [\"...\"]}\n\n"
        f"{json.dumps(compact_context, indent=2)}"
    )

    try:
        return _call_llm(prompt)
    except Exception:
        return []


def _call_llm(prompt: str) -> list[str]:
    import requests
    endpoint = os.environ.get("LLM_INSIGHTS_ENDPOINT", "http://localhost:11434/api/generate")
    resp = requests.post(
        endpoint,
        json={"model": os.environ.get("LLM_INSIGHTS_MODEL", "qwen3:8b"), "prompt": prompt, "stream": False},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    parsed = json.loads(data["response"])
    return list(parsed.get("insights", []))[:5]
