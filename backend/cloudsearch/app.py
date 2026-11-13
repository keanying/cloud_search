"""FastAPI 应用入口：uvicorn cloudsearch.app:app"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.routers import admin_llm, artifacts, auth, conversations, tasks, viewer
from .core.config import get_settings
from .db.base import create_all, dispose_engine

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
log = logging.getLogger("cloudsearch")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.auto_create_tables:
        await create_all()
    worker_task = None
    worker = None
    if s.embedded_worker:
        from .worker.main import Worker

        worker = Worker()
        worker_task = asyncio.create_task(worker.run_forever())
    try:
        yield
    finally:
        if worker:
            worker.stop()
            worker_task.cancel()
            from .browser.pool import get_pool

            await get_pool().close()
        await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(title="云搜浏览器 API", version="0.1.0", lifespan=lifespan)
    for r in (auth.router, conversations.router, tasks.router, viewer.router, artifacts.router, admin_llm.router):
        app.include_router(r, prefix="/api/v1")

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    return app


app = create_app()
