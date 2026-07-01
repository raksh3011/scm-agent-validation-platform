"""Builds the runtime environment for a workspace: installs deps best-effort,
bootstraps a synthetic SQLite database, and infers environment variables."""
import os
import subprocess
import sys
from pathlib import Path

from .detector import RepoProfile
from ..connectors import mock_erp, mock_wms
from ..core.config import DB_BOOTSTRAP_TIMEOUT_SECONDS, DEPENDENCY_INSTALL_TIMEOUT_SECONDS
from ..core.models import RuntimeEnvironment

# Heuristic match for a repo's own "populate my database" script — e.g.
# setup_smartreorder_db.py, init_db.py, seed_database.py. Run once, best-effort,
# before any scenario execution so the agent's own bundled (often empty/schema-only)
# SQLite file actually has data when the agent's entrypoint reads from it.
_DB_BOOTSTRAP_KEYWORDS = ("setup", "init", "seed", "bootstrap", "create")

SAFE_ENV_DEFAULTS = {
    "ERP_API_URL": "http://localhost:9999/mock-erp",
    "WMS_API_URL": "http://localhost:9999/mock-wms",
    "DATABASE_URL": "sqlite:///sandbox.db",
    "OPENAI_API_KEY": "sk-mock-disabled",
    "ANTHROPIC_API_KEY": "sk-mock-disabled",
    "ENV": "sandbox",
}


def install_dependencies(workspace: Path, profile: RepoProfile) -> list[str]:
    """Best-effort install into the current interpreter; failures don't abort the run
    because the validator must still attempt function-level execution."""
    log = []
    for req_file in profile.dependency_files:
        if req_file.name.startswith("requirements"):
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)],
                    capture_output=True, text=True, timeout=DEPENDENCY_INSTALL_TIMEOUT_SECONDS,
                )
                log.append(f"installed {req_file.name}")
            except Exception as e:
                log.append(f"failed installing {req_file.name}: {e}")
    return log


def run_db_bootstrap_scripts(workspace: Path) -> list[str]:
    log = []
    for path in sorted(workspace.glob("*.py")):
        name = path.stem.lower()
        if "db" not in name:
            continue
        if not any(kw in name for kw in _DB_BOOTSTRAP_KEYWORDS):
            continue
        try:
            proc = subprocess.run(
                [sys.executable, str(path)], cwd=str(workspace),
                capture_output=True, text=True, timeout=DB_BOOTSTRAP_TIMEOUT_SECONDS,
            )
            log.append(f"ran {path.name} (exit {proc.returncode})")
        except Exception as e:
            log.append(f"failed running {path.name}: {e}")
    return log


def build_sandbox_db(workspace: Path) -> Path:
    db_path = workspace / ".sandbox" / "sandbox.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    mock_erp.bootstrap(db_path)
    mock_wms.bootstrap(db_path)
    return db_path


def build_environment(workspace: Path, profile: RepoProfile) -> RuntimeEnvironment:
    install_log = install_dependencies(workspace, profile)
    bootstrap_log = run_db_bootstrap_scripts(workspace)
    db_path = build_sandbox_db(workspace)
    synthetic = {
        "inventory": mock_erp.get_inventory_snapshot(db_path),
        "suppliers": mock_erp.get_suppliers(db_path),
        "demand_history": mock_erp.get_demand_history(db_path),
        "warehouses": mock_wms.get_warehouses(db_path),
    }
    env_vars = {**os.environ, **SAFE_ENV_DEFAULTS, "DATABASE_URL": f"sqlite:///{db_path}"}

    return RuntimeEnvironment(
        workspace=workspace,
        language=profile.language,
        framework=profile.framework,
        entrypoint=None,
        sandbox_db_path=db_path,
        env_vars=env_vars,
        synthetic_data={**synthetic, "install_log": install_log, "db_bootstrap_log": bootstrap_log},
    )
