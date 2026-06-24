from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .api.runs import router as runs_router

# Initialize DB on module load
db.init_db()

app = FastAPI(title="SCM Agent Validation Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
