"""执行日志：每个任务一个可读的日志文件（logs/tasks/<task_id>.log），用于排查问题（可在页面下载后发给开发者）。

每行：时间  [事件]  说明  {细节 JSON}
记录：任务需求与关键配置、每个步骤（耗时/错误）、每次搜索（各引擎结果与失败原因）、每个网页读取（状态/原因）、
人机验证判定（命中的规则与证据截图）、每次模型调用（模型/耗时/token/错误）、人工接手、最终结果与异常堆栈。
不记录 API Key、密码；默认不记录提示词全文（logs.include_prompts 可开启）。
同时把全局日志写入 logs/app.log（滚动保留）。
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import threading
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT

current_task: ContextVar[str | None] = ContextVar("cs_current_task", default=None)
_lock = threading.Lock()
_app_logging_ready = False


def logs_dir() -> Path:
    from .config import get_settings

    d = get_settings().logs_dir
    return d if d.is_absolute() else PROJECT_ROOT / d


def trace_path(task_id: str) -> Path:
    return logs_dir() / "tasks" / f"{task_id}.log"


def trace(event: str, message: str, *, task_id: str | None = None, **fields: Any) -> None:
    """写一行任务执行日志；不在任务上下文中（且未指定 task_id）时忽略。永不抛异常。"""
    tid = task_id or current_task.get()
    if not tid:
        return
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        extra = {k: v for k, v in fields.items() if v is not None}
        line = f"{ts}  [{event}]  {message}"
        if extra:
            line += "  " + json.dumps(extra, ensure_ascii=False, default=str)
        p = trace_path(tid)
        with _lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(line.replace("\n", "\\n") + "\n")
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).debug("trace write failed", exc_info=True)


def setup_app_logging() -> None:
    """全局日志同时写入 logs/app.log（10MB × 5 份滚动）。"""
    global _app_logging_ready
    if _app_logging_ready:
        return
    try:
        d = logs_dir()
        d.mkdir(parents=True, exist_ok=True)
        h = logging.handlers.RotatingFileHandler(d / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5,
                                                 encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        h.setLevel(logging.INFO)
        root = logging.getLogger()
        root.addHandler(h)
        if root.level > logging.INFO or root.level == logging.NOTSET:
            root.setLevel(logging.INFO)
        _app_logging_ready = True
    except Exception:  # noqa: BLE001
        pass


def config_summary() -> dict[str, Any]:
    """排查用的关键配置（不含密钥/密码）。"""
    from .config import get_settings

    s = get_settings()
    return {
        "browser": {"headless": s.browser_headless, "channel": s.browser_channel, "proxy": bool(s.browser_proxy),
                    "locale": s.browser_locale, "takeover": s.browser_takeover_enabled},
        "search": {"engines": s.search_engines, "strategy": s.search_strategy,
                   "vertical": s.search_vertical_sources, "per_query": s.search_results_per_query},
        "task": {"max_sources": s.task_max_sources, "max_queries": s.task_max_queries,
                 "read_concurrency": s.task_read_concurrency, "max_extra_waves": s.task_max_extra_waves},
        "files": {"parser": s.files_parser, "mineru_local": s.mineru_local, "mineru_api": bool(s.mineru_api_url),
                  "mineru_tier": s.mineru_tier, "max_segments": s.files_max_segments},
        "privacy_local_only": s.privacy_data_local_only,
        "db": s.database_url.split(":", 1)[0],
    }
