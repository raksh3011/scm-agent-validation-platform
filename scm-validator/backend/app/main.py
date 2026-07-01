from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core import db
from .api.ci import router as ci_router
from .api.history import router as history_router
from .api.keys import router as keys_router
from .api.reports import router as reports_router
from .api.runs import router as runs_router

db.init_db()

app = FastAPI(title="SCM AI Agent Assurance Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_origins=[
        "https://scm-ai-agents-validator.vercel.app",
        "https://scm-ai-agents-validator-e382ke4x0-rakshakkm3011-9499s-projects.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Access control: every run/history/report endpoint requires an X-API-Key header
# (see core/auth.require_owner) and results are scoped to the caller's own key —
# no cross-user history leakage, no single shared secret. /api/keys itself is
# the one open endpoint since its job is handing out that first key.
app.include_router(keys_router)
app.include_router(runs_router)
app.include_router(reports_router)
app.include_router(history_router)
app.include_router(ci_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
