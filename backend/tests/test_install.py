"""安装相关：requirements.txt 与 uv.lock 一致；浏览器内核选择。"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_requirements_txt_matches_uv_lock():
    """依赖变更后需重新导出：uv export --frozen --no-emit-project --all-groups -o requirements.txt"""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked = {p["name"]: p["version"] for p in lock["package"] if p["name"] != "cloudsearch"}
    pinned = dict(re.findall(r"^([A-Za-z0-9_.\-]+)==([^\s;\\]+)", (ROOT / "requirements.txt").read_text(encoding="utf-8"),
                             re.M))
    norm = lambda n: re.sub(r"[-_.]+", "-", n).lower()  # noqa: E731
    pinned = {norm(k): v for k, v in pinned.items()}
    missing = {n: v for n, v in locked.items() if pinned.get(norm(n)) != v}
    assert not missing, f"requirements.txt 与 uv.lock 不一致，请重新导出：{missing}"


def test_browser_choice(env, monkeypatch, tmp_path):
    from cloudsearch.browser import launch
    from cloudsearch.core import config

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    monkeypatch.setattr(launch, "system_browser", lambda ch: "C:/Edge/msedge.exe" if ch == "msedge" else None)
    assert launch.resolve()["launch_kwargs"] == {"channel": "msedge"}  # auto：无自带 Chromium → 系统 Edge
    (tmp_path / "chromium-1243").mkdir()
    assert launch.resolve()["mode"] == "bundled"  # 已下载自带 Chromium 时优先使用
    monkeypatch.setenv("CS_BROWSER_CHANNEL", "chrome")
    config.get_settings.cache_clear()
    assert launch.resolve()["launch_kwargs"] == {"channel": "chrome"}
    monkeypatch.setenv("CS_BROWSER_EXECUTABLE_PATH", str(tmp_path / "nope.exe"))
    config.get_settings.cache_clear()
    assert launch.resolve()["mode"] == "error"
    monkeypatch.delenv("CS_BROWSER_EXECUTABLE_PATH")
    monkeypatch.setenv("CS_BROWSER_CHANNEL", "auto")
    config.get_settings.cache_clear()
    (tmp_path / "chromium-1243").rmdir()
    monkeypatch.setattr(launch, "system_browser", lambda ch: None)
    assert launch.resolve()["mode"] == "missing"


def test_wait_health_ignores_proxy(monkeypatch):
    """系统/环境代理不应影响对本机服务的健康检查（Windows 上 Clash 等代理会接管 127.0.0.1）。"""
    import http.server
    import threading

    import importlib.util

    spec = importlib.util.spec_from_file_location("cs_run", ROOT / "run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")  # 不可用的代理
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    try:
        ok, why = run.wait_health(f"http://127.0.0.1:{srv.server_port}/api/health", timeout=5)
        assert ok, why
    finally:
        srv.shutdown()
