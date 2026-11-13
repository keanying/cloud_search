"""决定用哪个浏览器内核启动：自带 Chromium / 系统 Edge / 系统 Chrome / 指定路径。

config.yaml:
  browser.channel: auto | bundled | msedge | chrome
  browser.executable_path: 可选，指定浏览器可执行文件

auto：自带 Chromium 已安装则用它；否则用系统已安装的 Edge（Windows 自带）或 Chrome；都没有才需要下载。
命令行：python -m cloudsearch.browser.launch   → 输出 JSON，供启动脚本判断是否需要下载 Chromium
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from ..core.config import get_settings

_SYSTEM_PATHS: dict[str, list[str]] = {
    "msedge": [
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
        r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/opt/microsoft/msedge/msedge",
    ],
    "chrome": [
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/opt/google/chrome/chrome",
    ],
}


def system_browser(channel: str) -> str | None:
    for raw in _SYSTEM_PATHS.get(channel, []):
        p = os.path.expandvars(raw)
        if "%" not in p and Path(p).is_file():
            return p
    return None


def bundled_installed() -> bool:
    root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or _default_browsers_path())
    return root.is_dir() and any(c.name.startswith("chromium") and not c.name.startswith("chromium_headless")
                                 for c in root.iterdir())


def _default_browsers_path() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def resolve() -> dict:
    """返回 {mode, launch_kwargs, detail}；mode=missing 表示需要下载自带 Chromium。"""
    s = get_settings()
    if s.browser_executable_path:
        p = Path(s.browser_executable_path)
        if not p.is_file():
            return {"mode": "error", "launch_kwargs": {}, "detail": f"browser.executable_path 不存在：{p}"}
        return {"mode": "executable", "launch_kwargs": {"executable_path": str(p)}, "detail": str(p)}
    channel = (s.browser_channel or "auto").lower()
    if channel in ("msedge", "chrome"):
        found = system_browser(channel)
        return {"mode": "channel", "launch_kwargs": {"channel": channel},
                "detail": found or f"{channel}（由 Playwright 查找）"}
    if channel == "bundled" or bundled_installed():
        return {"mode": "bundled" if bundled_installed() else "missing", "launch_kwargs": {},
                "detail": "Playwright 自带 Chromium"}
    if channel != "auto":
        return {"mode": "error", "launch_kwargs": {}, "detail": f"browser.channel 只能是 auto/bundled/msedge/chrome：{channel}"}
    for ch in ("msedge", "chrome"):
        found = system_browser(ch)
        if found:
            return {"mode": "channel", "launch_kwargs": {"channel": ch}, "detail": found}
    return {"mode": "missing", "launch_kwargs": {}, "detail": "未找到可用浏览器，需要下载 Chromium"}


if __name__ == "__main__":
    print(json.dumps(resolve(), ensure_ascii=False))
