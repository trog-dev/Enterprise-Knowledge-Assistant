from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from qdrant_client import QdrantClient

from app.core.config import get_settings
from app.db.session import engine

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
def liveness():
    return {"status": "ok"}


@router.get("/health/ready")
def readiness():
    checks = {"database": "disconnected", "qdrant": "disconnected"}

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception:
        pass

    try:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=3,
        )
        client.get_collections()
        checks["qdrant"] = "connected"
        client.close()
    except Exception:
        pass

    ready = all(value == "connected" for value in checks.values())
    payload = {"status": "ready" if ready else "not_ready", "checks": checks}
    return JSONResponse(status_code=200 if ready else 503, content=payload)
