"""FastAPI app factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .keystore import all_keys
from .log import configure_logging, get_logger
from .providers import get_registry
from .providers._http import close_client
from .routes import agents as agents_routes
from .routes import chat as chat_routes
from .routes import memory as memory_routes
from .routes import onboarding as onboarding_routes
from .routes import tools as tools_routes

configure_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("backend.startup", host=settings.host, port=settings.port, data_dir=str(settings.data_dir))
    await get_registry().load(all_keys())
    yield
    await close_client()
    log.info("backend.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Overlord",
        version="0.1.0",
        description="Autonomous multi-provider AI agent council",
        lifespan=lifespan,
    )
    # Electron renderer talks to us over localhost; allow it freely.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(onboarding_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(agents_routes.router)
    app.include_router(memory_routes.router)
    app.include_router(tools_routes.router)

    @app.get("/health")
    def health():
        reg = get_registry()
        return {
            "ok": True,
            "providers": [p.name for p in reg.providers()],
            "has_keys": reg.has_any(),
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level,
    )
