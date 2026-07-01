from pydantic import BaseModel


class ScenarioLevel(BaseModel):
    name: str
    description: str
    params: dict
    severity_if_failed: str = "medium"


class ScenarioAxis(BaseModel):
    axis: str
    category: str
    applies_to: list[str]
    levels: list[ScenarioLevel]


class RulePack(BaseModel):
    pack_name: str
    axes: list[ScenarioAxis]
