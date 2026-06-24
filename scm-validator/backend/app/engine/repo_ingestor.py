"""Turns a submission (repo URL / zip / loose files) into a local workspace directory."""
import shutil
import subprocess
import zipfile
from pathlib import Path

STORAGE_ROOT = Path(__file__).resolve().parent.parent.parent / "storage"
WORKSPACES = STORAGE_ROOT / "workspaces"

IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".cache"}


def workspace_path(run_id: str) -> Path:
    p = WORKSPACES / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def ingest_repo_url(run_id: str, repo_url: str) -> Path:
    dest = workspace_path(run_id)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(dest)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr.strip()[:500]}")
    return dest


def ingest_zip(run_id: str, zip_path: Path) -> Path:
    dest = workspace_path(run_id)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)
    return dest


def ingest_files(run_id: str, files: list[tuple[str, bytes]]) -> Path:
    dest = workspace_path(run_id)
    for filename, content in files:
        target = dest / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return dest


def list_source_files(root: Path) -> list[Path]:
    out = []
    for path in root.rglob("*"):
        if path.is_file() and not any(part in IGNORE_DIRS for part in path.parts):
            out.append(path)
    return out


def cleanup_workspace(run_id: str):
    p = WORKSPACES / run_id
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)
