"""服务入口在“asyncio.run 被调试器替换”时仍能启动（复现 PyCharm 2024.3 调试模式的问题）。"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

# 模拟 pydevd 的 _patch_asyncio：替换后的 asyncio.run 不接受 loop_factory
PATCH_AND_RUN = """
import asyncio, runpy, sys
_orig = asyncio.run
def run(main, *, debug=None):
    return _orig(main, debug=debug)
asyncio.run = run
sys.argv = ["cloudsearch.serve", "--host", "127.0.0.1", "--port", sys.argv[1]]
runpy.run_module("cloudsearch.serve", run_name="__main__", alter_sys=True)
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_serve_starts_when_asyncio_run_is_patched(tmp_path):
    port = _free_port()
    env = {**os.environ, "CS_CONFIG_FILE": str(tmp_path / "none.yaml"), "CS_EMBEDDED_WORKER": "false",
           "CS_DATABASE_URL": f"sqlite+aiosqlite:///{(tmp_path / 't.db').as_posix()}",
           "CS_STORAGE_DIR": str(tmp_path / "st"), "CS_WEB_DIST_DIR": str(tmp_path / "nodist")}
    p = subprocess.Popen([sys.executable, "-c", PATCH_AND_RUN, str(port)], env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    try:
        body = None
        for _ in range(60):
            if p.poll() is not None:
                break
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as r:
                    body = json.loads(r.read())
                    break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        assert body == {"ok": True, "db": "ok", "embedded_worker": False}, p.stdout.read() if p.poll() else body
    finally:
        p.terminate()
        p.wait(timeout=20)


def test_run_coro_cleans_up_pending_tasks():
    import asyncio

    from cloudsearch.serve import run_coro

    started = []

    async def bg():
        started.append(1)
        await asyncio.sleep(100)

    async def main():
        asyncio.get_running_loop().create_task(bg())
        await asyncio.sleep(0)
        return 42

    assert run_coro(main()) == 42 and started == [1]
