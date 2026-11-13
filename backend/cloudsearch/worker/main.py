"""云端 worker：领取对话轮次与任务运行并执行。可独立运行（python -m cloudsearch.worker.main），
开发模式下也可嵌入 API 进程（CS_EMBEDDED_WORKER=true）。"""

from __future__ import annotations

import asyncio
import logging
import signal

from ..core.config import get_settings
from ..orchestrator.runner import claim_run, execute_run
from ..services.turns import claim_turn, process_turn

log = logging.getLogger("cloudsearch.worker")

MAX_CONCURRENT_TURNS = 4


class Worker:
    def __init__(self, worker_id: str | None = None):
        s = get_settings()
        self.worker_id = worker_id or s.worker_id
        self.runs: set[asyncio.Task] = set()
        self.turns: set[asyncio.Task] = set()
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def tick(self) -> bool:
        """领取一轮工作；返回是否领取到任何东西。"""
        s = get_settings()
        got = False
        while len(self.turns) < MAX_CONCURRENT_TURNS:
            mid = await claim_turn(self.worker_id)
            if not mid:
                break
            got = True
            t = asyncio.create_task(process_turn(mid, self.worker_id), name=f"turn:{mid}")
            self.turns.add(t)
            t.add_done_callback(self.turns.discard)
        while len(self.runs) < s.worker_max_tasks:
            claimed = await claim_run(self.worker_id)
            if not claimed:
                break
            got = True
            run_id, epoch = claimed
            t = asyncio.create_task(execute_run(run_id, epoch, self.worker_id), name=f"run:{run_id}")
            self.runs.add(t)
            t.add_done_callback(self.runs.discard)
        return got

    async def run_forever(self) -> None:
        interval = get_settings().worker_poll_interval_s
        log.info("worker %s started", self.worker_id)
        while not self._stop.is_set():
            try:
                got = await self.tick()
            except Exception:  # noqa: BLE001
                log.exception("worker tick failed")
                got = False
            if not got:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=interval)
                except TimeoutError:
                    pass
        for t in list(self.runs | self.turns):
            t.cancel()

    async def drain(self) -> None:
        """测试用：等待当前所有工作完成。"""
        while self.runs or self.turns:
            await asyncio.gather(*(self.runs | self.turns), return_exceptions=True)
            await self.tick()


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # 数据库迁移由启动脚本 / API 负责，worker 不做迁移，避免多进程同时迁移
    from ..app import sync_config_to_db

    await sync_config_to_db()
    w = Worker()
    from ..browser.live_server import start_internal_server

    live_task = await start_internal_server()  # 供 API 转发实时画面与人工接管输入
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, w.stop)
        except NotImplementedError:  # Windows 不支持，Ctrl+C 以 KeyboardInterrupt 结束
            pass
    try:
        await w.run_forever()
    finally:
        live_task.cancel()
        from ..browser.pool import get_pool

        await get_pool().close()


if __name__ == "__main__":
    from ..serve import run_coro

    run_coro(_main())  # 不用 asyncio.run：兼容 PyCharm 调试模式
