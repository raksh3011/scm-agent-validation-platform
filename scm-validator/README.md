# SCM Agent Validation Platform

A lightweight, deterministic-first validation platform for SCM (supply chain) AI agents.
Upload an agent's code (files, ZIP, or a repo URL) and get a trust score, positive
signals, defects, and recommended fixes — rendered directly in a dashboard, not as a
static report file.

## Stack

- **Backend**: FastAPI + SQLite (`backend/`)
- **Frontend**: Next.js + TypeScript (`frontend/`)
- **Validation engine**: modular Python, deterministic-first (`backend/app/engine/`)

## Why deterministic-first

The official trust score and findings come from fixed, auditable rules over the
agent's code structure (LLM call safety, error handling, SCM logic patterns,
documentation, etc.), not from an LLM grading itself. An optional AI insights layer
can add commentary, but it never changes the score.

## Running locally

### Backend

```bash
cd backend
python -m venv .venv
./.venv/Scripts/activate   # or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open `http://localhost:3000/new` to submit an agent for validation.

## API

- `POST /api/runs` — submit a repo URL, ZIP, or files
- `GET /api/runs/{run_id}/status` — poll validation progress
- `GET /api/runs/{run_id}/results` — structured validation result (same data the dashboard renders)
- `GET /api/runs` — validation history

## Validation dimensions

Specification Completeness, Reliability & Error Handling, AI/LLM Risk Controls,
SCM Logic Quality, Observability/Traceability, Demo Readiness, Production Readiness.
