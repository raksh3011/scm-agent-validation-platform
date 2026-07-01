"""Turns a submission (repo URL / zip / loose files) into a local workspace directory.

Every ingestion path here takes attacker-controlled input (a URL, a zip a user
uploaded, filenames a user chose) and writes it to disk or hands it to a
subprocess — each function validates its input defensively rather than trusting
it, since this is the platform's actual external attack surface.
"""
import ipaddress
import re
import shutil
import socket
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from ..core.config import WORKSPACES_DIR

IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".cache", ".sandbox"}

# Only plain http(s) URLs are allowed through to `git clone`. Git supports a
# number of other transports (ext::, file://, the fetch/upload-pack helper
# protocols) that can be abused to execute arbitrary local commands when the
# URL is attacker-controlled — e.g. `ext::sh -c 'touch pwned'` is a well-known
# git RCE vector. A leading "-" is rejected too, since git would otherwise
# interpret the "URL" as a command-line option (argument injection).
_ALLOWED_REPO_URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
MAX_ZIP_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200 MB cap against zip-bomb DoS
MAX_ZIP_ENTRY_COUNT = 5000
WORKSPACE_RETENTION_DAYS = 7


def workspace_path(run_id: str) -> Path:
    p = WORKSPACES_DIR / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _reject_ssrf_targets(hostname: str) -> None:
    """Resolve the URL's hostname and reject anything that lands in a private,
    loopback, or link-local range — without this, `repo_url` is a server-side
    request forgery primitive: an attacker can point it at the cloud metadata
    endpoint (169.254.169.254), an internal admin service, or localhost, and
    the platform's own server makes that request on the attacker's behalf
    during the git clone handshake."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise ValueError(f"Could not resolve repository host {hostname!r}: {e}")
    for family, _, _, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise ValueError(
                f"Repository host {hostname!r} resolves to a non-public address ({ip}) — rejected."
            )


def _validate_repo_url(repo_url: str) -> str:
    repo_url = repo_url.strip()
    if repo_url.startswith("-") or not _ALLOWED_REPO_URL_RE.match(repo_url):
        raise ValueError(
            "Invalid repository URL — only plain http:// or https:// URLs are accepted."
        )
    hostname = urlsplit(repo_url).hostname
    if not hostname:
        raise ValueError("Invalid repository URL — no hostname found.")
    _reject_ssrf_targets(hostname)
    return repo_url


def ingest_repo_url(run_id: str, repo_url: str) -> Path:
    repo_url = _validate_repo_url(repo_url)
    dest = workspace_path(run_id)
    result = subprocess.run(
        # The "--" separator guarantees git treats everything after it as a
        # positional argument, never as an option, even in the face of a
        # validation bug above — defense in depth, not the only check.
        ["git", "-c", "protocol.ext.allow=never", "clone", "--depth", "1", "--", repo_url, str(dest)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr.strip()[:500]}")
    return dest


def _safe_extract_path(dest: Path, member_name: str) -> Path:
    """Resolve a zip/tar member's target path and reject it if it would land
    outside `dest` — the classic "zip-slip" path-traversal vulnerability,
    where an entry named e.g. `../../../../etc/cron.d/evil` escapes the
    intended extraction directory."""
    target = (dest / member_name).resolve()
    dest_resolved = dest.resolve()
    if target != dest_resolved and dest_resolved not in target.parents:
        raise ValueError(f"Rejected zip entry with unsafe path: {member_name!r}")
    return target


def ingest_zip(run_id: str, zip_path: Path) -> Path:
    dest = workspace_path(run_id)
    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_ENTRY_COUNT:
            raise ValueError(f"Zip contains too many entries (> {MAX_ZIP_ENTRY_COUNT}).")
        total_uncompressed = sum(i.file_size for i in infos)
        if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise ValueError("Zip's uncompressed size exceeds the allowed limit.")
        for info in infos:
            target = _safe_extract_path(dest, info.filename)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    return dest


def ingest_files(run_id: str, files: list[tuple[str, bytes]]) -> Path:
    dest = workspace_path(run_id)
    for filename, content in files:
        # Browsers normally send just a basename, but the multipart filename
        # field is fully attacker-controlled — treat it the same as a zip
        # member name rather than trusting it.
        target = _safe_extract_path(dest, filename)
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
    p = WORKSPACES_DIR / run_id
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)


def cleanup_stale_workspaces(max_age_days: int = WORKSPACE_RETENTION_DAYS) -> int:
    """Every submitted repo/zip/file set — third-party source code that may
    contain secrets or proprietary IP — was being retained on disk forever;
    `cleanup_workspace` existed but was never called anywhere. Run this
    opportunistically (called once per new submission) to purge anything past
    the retention window instead of needing a separate cron/scheduler process.
    Best-effort: a workspace that fails to delete (e.g. still in use) is
    skipped rather than raising, since this must never block a new run."""
    import time

    if not WORKSPACES_DIR.exists():
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for entry in WORKSPACES_DIR.iterdir():
        try:
            if entry.stat().st_mtime < cutoff:
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
                removed += 1
        except OSError:
            continue
    return removed


def repo_content_hash(root: Path) -> str:
    """Stable hash of file contents (sorted by relative path) used to seed deterministic scenario generation."""
    import hashlib
    h = hashlib.sha256()
    for path in sorted(list_source_files(root), key=lambda p: str(p.relative_to(root))):
        try:
            h.update(str(path.relative_to(root)).encode())
            h.update(path.read_bytes())
        except OSError:
            continue
    return h.hexdigest()
