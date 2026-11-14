"""服务入口：python -m cloudsearch.serve [--host H] [--port P]

不直接用 `uvicorn` 命令 / asyncio.run：PyCharm 调试模式（pydevd --multiprocess）会替换子进程中的
asyncio.run，且其替换版本不支持新版 uvicorn 传入的 loop_factory 参数，导致启动失败。
这里自己创建事件循环（Windows 上为 ProactorEventLoop，Playwright 启动浏览器需要它），与调试器兼容。
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Callable, Coroutine
from typing import Any

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")


def run_coro(coro: Coroutine[Any, Any, Any],
             loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None) -> Any:
    """等价于 asyncio.run(coro, loop_factory=...)，但不调用 asyncio.run（避免被调试器替换的版本）。"""
    loop = loop_factory() if loop_factory else asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for t in pending:
                t.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            asyncio.set_event_loop(None)
            loop.close()


def main() -> None:
    import uvicorn

    from .core.config import get_settings

    from .core.tracelog import setup_app_logging

    s = get_settings()
    setup_app_logging()
    ap = argparse.ArgumentParser(description="云搜浏览器 API 服务")
    ap.add_argument("--host", default=s.server_host)
    ap.add_argument("--port", type=int, default=s.server_port)
    ap.add_argument("--forwarded-allow-ips", default="127.0.0.1", help="可信反向代理地址（用于 X-Forwarded-*）")
    args = ap.parse_args()

    config = uvicorn.Config("cloudsearch.app:app", host=args.host, port=args.port, proxy_headers=True,
                            forwarded_allow_ips=args.forwarded_allow_ips, log_level="info")
    server = uvicorn.Server(config)
    run_coro(server.serve(), config.get_loop_factory())


if __name__ == "__main__":
    main()
