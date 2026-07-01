"""Thin re-export shim — the actual 9-stage pipeline lives in stage_runner.py. Kept so
existing imports (`from ..pipeline import orchestrator`) don't need to change."""
from .stage_runner import (  # noqa: F401
    mark_failed,
    persist_result,
    subject_id_for,
)
from .stage_runner import run as run_validation  # noqa: F401
