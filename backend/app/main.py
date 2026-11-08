from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import get_settings
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.search import router as search_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Enterprise RAG platform — foundation phase.",
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(search_router)
app.include_router(chat_router)
app.include_router(conversations_router)

@app.get("/", tags=["root"])
def root():
    return {
        "message": "Enterprise Knowledge Assistant API",
        "docs": "/docs",
        "health": "/health",
    }
