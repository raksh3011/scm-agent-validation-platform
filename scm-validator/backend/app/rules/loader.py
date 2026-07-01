"""Discovers and loads rule packs from rules/packs/*.yaml. New domains are added by
dropping a new YAML file here — no validator code changes needed."""
from pathlib import Path

import yaml

from .schema import RulePack, ScenarioAxis

PACKS_DIR = Path(__file__).resolve().parent / "packs"


def load_packs() -> list[RulePack]:
    packs = []
    for path in sorted(PACKS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        packs.append(RulePack(**data))
    return packs


def axes_for_agent_type(agent_type: str, packs: list[RulePack] | None = None) -> list[ScenarioAxis]:
    packs = packs or load_packs()
    axes = []
    for pack in packs:
        for axis in pack.axes:
            if agent_type in axis.applies_to:
                axes.append(axis)
    return axes
