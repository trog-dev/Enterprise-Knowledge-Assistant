# Enterprise Knowledge Assistant — Phase 1

Starter foundation for an end-to-end Enterprise RAG application.

## Stack
- Backend: Python 3.9.12, FastAPI, SQLAlchemy, PostgreSQL
- Vector database: Qdrant
- Frontend: React + TypeScript + Vite
- Local infrastructure: Docker Compose

## Prerequisites
- Python 3.9.12
- Node.js 20 LTS (or a compatible Node.js release supported by Vite)
- Docker Desktop with Docker Compose
- VS Code

## 1. Backend setup (PowerShell)

```powershell
py -3.9 --version
py -3.9 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks activation, run this once in the current terminal:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 2. Start PostgreSQL and Qdrant

```powershell
docker compose up -d postgres qdrant
docker compose ps
```

## 3. Run the API

```powershell
uvicorn backend.app.main:app --reload
```

Open:
- API docs: http://127.0.0.1:8000/docs
- Liveness: http://127.0.0.1:8000/health
- Readiness: http://127.0.0.1:8000/health/ready

Readiness checks the PostgreSQL and Qdrant connections.

## 4. Run the frontend

Open a second terminal:
```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite (normally http://localhost:5173).

## 5. Stop infrastructure

```powershell
docker compose down
```

To also remove local database/vector data:
```powershell
docker compose down -v
```
WARNING: `-v` deletes the persisted local PostgreSQL and Qdrant data.

## Project layout

```text
backend/
  app/
    api/          # HTTP endpoints
    core/         # configuration
    db/           # database engine/session
    services/     # infrastructure health checks
    main.py
frontend/
  src/
docker-compose.yml
```

## Phase 1 acceptance checklist
- [ ] Python reports 3.9.12 and virtual environment is active.
- [ ] Dependencies install successfully.
- [ ] PostgreSQL and Qdrant containers are healthy.
- [ ] `/health` returns `{"status":"ok"}`.
- [ ] `/health/ready` reports database and Qdrant as connected.
- [ ] React starter page opens in the browser.

## Important
Do not commit `.env`, API keys, uploaded documents, database volumes, or model weights.
This starter does not yet implement document ingestion or RAG; those are later phases.
