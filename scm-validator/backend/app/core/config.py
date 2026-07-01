from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = BACKEND_ROOT / "storage"
WORKSPACES_DIR = STORAGE_ROOT / "workspaces"
UPLOADS_DIR = STORAGE_ROOT / "uploads"
REPORTS_DIR = STORAGE_ROOT / "reports"
DB_PATH = STORAGE_ROOT / "assurance.db"

for d in (STORAGE_ROOT, WORKSPACES_DIR, UPLOADS_DIR, REPORTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

SANDBOX_TIMEOUT_SECONDS = 8
SCENARIO_EXECUTION_TIMEOUT_SECONDS = 5
MAX_SCENARIOS_PER_RUN = 320
REPRODUCIBILITY_SAMPLE_SIZE = 12
DEPENDENCY_INSTALL_TIMEOUT_SECONDS = 120
DB_BOOTSTRAP_TIMEOUT_SECONDS = 20

# Upload size caps — without these, an unauthenticated client could submit an
# arbitrarily large multipart body and exhaust disk/memory (a cheap DoS vector).
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB per submitted source file / zip
MAX_ASD_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB for a specification document
