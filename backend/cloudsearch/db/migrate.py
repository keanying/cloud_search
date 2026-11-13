"""启动时自动迁移（database.auto_create_tables=true 时使用，替代直接建表）。

- 新库：从头执行全部迁移
- 已由 alembic 管理的库：升级到最新
- 早期版本直接建表、没有 alembic_version 的库：按现有表结构判断属于哪个版本，先标记（stamp）再升级
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from ..core.config import BACKEND_ROOT
from .base import get_engine

log = logging.getLogger(__name__)

INITIAL_REVISION = "ced47a1e1f60"
# 按时间顺序：(版本号, 判断“该版本的结构已存在”的函数)。新增迁移时在末尾追加一项。
SCHEMA_MARKERS: list[tuple[str, callable]] = [
    (INITIAL_REVISION, lambda insp: insp.has_table("src_opr_task_f")),
    ("e61a8fd44241", lambda insp: "supports_forced_tool_choice" in
     {c["name"] for c in insp.get_columns("src_opr_llm_model_f")}),
    ("57f4cb6bf707", lambda insp: "handoff_state" in {c["name"] for c in insp.get_columns("src_opr_browser_session_f")}),
]


def alembic_config() -> Config:
    # 不读取 alembic.ini：避免 Windows 中文系统按本地编码（GBK）读取配置文件出错；迁移目录直接在代码中指定
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(BACKEND_ROOT / "migrations")))
    cfg.attributes["configure_logger"] = False
    return cfg


def _detect_unmanaged_revision(sync_conn) -> str | None:
    """返回无 alembic_version 的已有库对应的版本；空库返回 None。"""
    insp = inspect(sync_conn)
    if insp.has_table("alembic_version"):
        return "managed"
    found = None
    for rev, present in SCHEMA_MARKERS:
        try:
            if present(insp):
                found = rev
            else:
                break
        except Exception:  # noqa: BLE001  表不存在等
            break
    return found


async def auto_migrate() -> None:
    async with get_engine().connect() as conn:
        state = await conn.run_sync(_detect_unmanaged_revision)
    cfg = alembic_config()
    if state not in (None, "managed"):
        log.info("existing database without migration history; stamping at %s", state)
        await asyncio.to_thread(command.stamp, cfg, state)
    # alembic 的 env.py 内部会自建事件循环，因此放到线程中执行
    await asyncio.to_thread(command.upgrade, cfg, "head")


if __name__ == "__main__":  # python -m cloudsearch.db.migrate
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from ..serve import run_coro

    run_coro(auto_migrate())
    print("数据库已是最新版本")
