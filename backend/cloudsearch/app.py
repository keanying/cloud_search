"""FastAPI 应用入口：uvicorn cloudsearch.app:app"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from .api.routers import admin_llm, artifacts, auth, conversations, tasks, viewer
from .core.config import get_settings
from .db.base import dispose_engine, get_engine, session_scope
from .db.migrate import auto_migrate

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
log = logging.getLogger("cloudsearch")


async def sync_config_to_db() -> None:
    """把 config.yaml 中的 llm 配置同步进数据库。"""
    from .llm.seed import sync_llm_config

    async with session_scope() as db:
        await sync_llm_config(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.auto_create_tables:
        await auto_migrate()  # 自动迁移到最新结构（已是最新时无操作）
    await sync_config_to_db()
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
        """进程与数据库健康检查（服务器脚本 check 命令使用）。"""
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
            db = "ok"
        except Exception as e:  # noqa: BLE001
            db = f"error: {type(e).__name__}"
        ok = db == "ok"
        return JSONResponse({"ok": ok, "db": db, "embedded_worker": get_settings().embedded_worker},
                            status_code=200 if ok else 503)

    _mount_web(app)
    return app


def _mount_web(app: FastAPI) -> None:
    """若存在前端打包产物（web/dist），由 API 同端口提供页面；单页应用路由回退到 index.html。"""
    dist = get_settings().web_dist_dir.resolve()
    index = dist / "index.html"
    if not index.is_file():
        return

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(dist):
            headers = {"Cache-Control": "public, max-age=31536000, immutable"} if full_path.startswith("assets/") else {}
            return FileResponse(candidate, headers=headers)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
