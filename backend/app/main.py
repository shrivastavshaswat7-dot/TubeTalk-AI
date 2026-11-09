import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, health, insights, sessions, videos
from app.core.config import get_settings
from app.core.errors import register_exception_handlers

logger = logging.getLogger("tubetalk")


def _warm_up_embeddings() -> None:
    try:
        from app.services.embeddings import embed_query

        embed_query("warm up")
        logger.info("Embedding model warmed up")
    except Exception:  # never let warm-up break the backend
        logger.warning("Embedding warm-up failed; the model will load on first use")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Background thread: startup (and /health) stay fast and cannot fail because of the model.
    if get_settings().warmup_embeddings:
        threading.Thread(target=_warm_up_embeddings, daemon=True, name="embedding-warmup").start()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="TubeTalk AI", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(videos.router)
    app.include_router(sessions.router)
    app.include_router(chat.router)
    app.include_router(insights.router)
    return app


app = create_app()
