#!/usr/bin/env python3
"""云搜浏览器 一键启动（Windows / macOS / Linux 通用，仅依赖 Python 标准库）。

步骤：检查环境 → 准备 config.yaml → 根目录 .venv 安装依赖 → 安装 Chromium → 前端安装与打包
     → 数据库迁移 → 启动服务（页面与接口同一端口）→ 打开浏览器

用法：
  python run.py                 一键准备并启动
  python run.py --setup-only    只安装/打包/迁移，不启动（服务器脚本 setup 使用）
  python run.py --dev           开发模式：额外启动前端热更新服务 (http://127.0.0.1:5173)
  python run.py --no-install    跳过依赖检查（已安装过时加快启动）
  python run.py --no-build      跳过前端打包
  python run.py --no-browser    不自动打开浏览器
  python run.py --rebuild       强制重新安装依赖并重新打包前端
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
WEB = ROOT / "web"
IS_WIN = os.name == "nt"
VENV_PY = VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")
PW_DIR = ROOT / ".playwright"
MIN_PY, MAX_PY = (3, 12), (3, 13)
MIN_NODE = 18

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ------------------------------------------------------------------ 输出与命令
def step(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def info(msg: str) -> None:
    print(f"    {msg}", flush=True)


def fail(msg: str, hint: str | None = None) -> None:
    print(f"\n[错误] {msg}", file=sys.stderr)
    if hint:
        print(f"       {hint}", file=sys.stderr)
    sys.exit(1)


def run(cmd: list[str], *, cwd: Path = ROOT, env: dict | None = None, check: bool = True) -> int:
    info("$ " + " ".join(str(c) for c in cmd))
    rc = subprocess.call([str(c) for c in cmd], cwd=str(cwd), env={**os.environ, **(env or {})})
    if check and rc != 0:
        fail(f"命令执行失败（退出码 {rc}）：{' '.join(str(c) for c in cmd)}")
    return rc


def file_hash(*paths: Path) -> str:
    h = hashlib.sha256()
    for p in paths:
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def stamp_ok(stamp: Path, value: str) -> bool:
    return stamp.exists() and stamp.read_text(encoding="utf-8").strip() == value


# ------------------------------------------------------------------ 安装源（读取 config.yaml 的 install 分区，无需 yaml 库）
def install_options() -> dict[str, str]:
    """从 config.yaml 中读取 install 分区的简单键值（pip_index_url / npm_registry / playwright_download_host）。"""
    opts: dict[str, str] = {}
    cfg = ROOT / "config.yaml"
    if not cfg.exists():
        return opts
    in_section = False
    for raw in cfg.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not raw.startswith((" ", "\t")):
            in_section = line.strip() == "install:"
            continue
        if in_section and ":" in line:
            k, v = line.strip().split(":", 1)
            v = v.strip().strip("'\"")
            if v:
                opts[k.strip()] = v
    return opts


# ------------------------------------------------------------------ 各步骤
def check_python() -> None:
    step(f"检查 Python（当前 {sys.version.split()[0]}）")
    if sys.version_info[:2] < MIN_PY:
        fail(f"需要 Python {MIN_PY[0]}.{MIN_PY[1]} 或更高版本", "请安装 Python 3.12 或 3.13：https://www.python.org/downloads/")
    if sys.version_info[:2] > MAX_PY:
        info(f"提示：已验证的版本是 3.12/3.13，当前 {sys.version_info[0]}.{sys.version_info[1]} 可能缺少部分依赖的预编译包")


def ensure_config() -> None:
    cfg = ROOT / "config.yaml"
    if not cfg.exists():
        shutil.copy(ROOT / "config.example.yaml", cfg)
        step("已根据 config.example.yaml 生成 config.yaml（数据库、密钥、大模型等请在此文件中维护）")


def ensure_venv(force: bool, opts: dict[str, str]) -> None:
    step("准备 Python 环境（仓库根目录 .venv）")
    want = file_hash(ROOT / "pyproject.toml", ROOT / "uv.lock")
    stamp = VENV / ".cloudsearch-deps"
    if not force and VENV_PY.exists() and stamp_ok(stamp, want):
        info("依赖已是最新，跳过")
        return
    env = {}
    if opts.get("pip_index_url"):
        env.update(PIP_INDEX_URL=opts["pip_index_url"], UV_INDEX_URL=opts["pip_index_url"],
                   UV_DEFAULT_INDEX=opts["pip_index_url"])
    uv = shutil.which("uv")
    if uv:
        info("使用 uv 按 uv.lock 安装（版本锁定）")
        run([uv, "sync", "--frozen", "--no-dev", "--python", sys.executable], env=env)
    else:
        if not VENV_PY.exists():
            run([sys.executable, "-m", "venv", str(VENV)])
        info("未检测到 uv，使用 pip 安装（安装 uv 可更快且版本锁定：pip install uv）")
        run([VENV_PY, "-m", "pip", "install", "--upgrade", "pip"], env=env)
        run([VENV_PY, "-m", "pip", "install", "-e", "."], env=env)
    stamp.write_text(want, encoding="utf-8")


def ensure_chromium(opts: dict[str, str]) -> None:
    step("准备云端浏览器 Chromium")
    browsers = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or PW_DIR)
    if browsers.is_dir() and any(p.name.startswith("chromium") for p in browsers.iterdir()):
        info(f"已安装：{browsers}")
        return
    env = {"PLAYWRIGHT_BROWSERS_PATH": str(browsers)}
    if opts.get("playwright_download_host"):
        env["PLAYWRIGHT_DOWNLOAD_HOST"] = opts["playwright_download_host"]
    cmd = [VENV_PY, "-m", "playwright", "install", "chromium"]
    if not IS_WIN and sys.platform != "darwin" and hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd.append("--with-deps")  # Linux root：顺带安装系统依赖库
    run(cmd, env=env)


def node_tools() -> tuple[list[str], str]:
    node = shutil.which("node")
    if not node:
        fail("未找到 Node.js", "请安装 Node.js 20 或 22 LTS：https://nodejs.org/ （安装后重新打开命令行窗口）")
    ver = subprocess.check_output([node, "--version"], text=True).strip().lstrip("v")
    if int(ver.split(".")[0]) < MIN_NODE:
        fail(f"Node.js 版本过低（{ver}），需要 {MIN_NODE}+", "请安装 Node.js 20 或 22 LTS")
    info(f"Node.js {ver}")
    if shutil.which("pnpm"):
        return [shutil.which("pnpm")], "pnpm"
    corepack = shutil.which("corepack")
    if corepack:
        os.environ["COREPACK_ENABLE_DOWNLOAD_PROMPT"] = "0"
        return [corepack, "pnpm"], "pnpm"
    return [shutil.which("npm")], "npm"


def ensure_web(force_install: bool, build: bool, force_build: bool, opts: dict[str, str]) -> list[str]:
    step("准备前端（Vue 3）")
    pm, kind = node_tools()
    env = {"npm_config_registry": opts["npm_registry"]} if opts.get("npm_registry") else {}
    want = file_hash(WEB / "package.json", WEB / "pnpm-lock.yaml")
    stamp = WEB / "node_modules" / ".cloudsearch-deps"
    if force_install or not stamp_ok(stamp, want):
        if kind == "pnpm":
            run(pm + ["install", "--frozen-lockfile"], cwd=WEB, env=env)
        else:
            info("未检测到 pnpm/corepack，改用 npm 安装（不使用锁文件）")
            run(pm + ["install"], cwd=WEB, env=env)
        stamp.write_text(want, encoding="utf-8")
    else:
        info("前端依赖已是最新，跳过")
    if build:
        index = WEB / "dist" / "index.html"
        sources = [WEB / "index.html", WEB / "package.json", WEB / "vite.config.ts", *(WEB / "src").rglob("*")]
        newest = max(p.stat().st_mtime for p in sources if p.is_file())
        if force_build or not index.exists() or index.stat().st_mtime < newest:
            step("打包前端")
            run(pm + ["run", "build"], cwd=WEB, env=env)
        else:
            info("前端打包已是最新，跳过")
    return pm


def app_config() -> dict:
    """用 .venv 读取并校验 config.yaml（有错会在这里提示）。"""
    code = ("import json;from cloudsearch.core.config import get_settings as g;s=g();"
            "print(json.dumps({'host':s.server_host,'port':s.server_port,'embedded':s.embedded_worker,"
            "'auto_create':s.auto_create_tables,'db':s.database_url.split(':',1)[0]}))")
    try:
        out = subprocess.check_output([str(VENV_PY), "-c", code], cwd=str(ROOT), text=True, stderr=subprocess.STDOUT,
                                      encoding="utf-8")
    except subprocess.CalledProcessError as e:
        fail("config.yaml 配置有误：\n" + e.output.strip().splitlines()[-1])
    return json.loads(out.strip().splitlines()[-1])


def migrate(cfg: dict) -> None:
    if cfg["auto_create"]:
        return
    step("执行数据库迁移（alembic upgrade head）")
    run([VENV_PY, "-m", "alembic", "-c", str(ROOT / "backend" / "alembic.ini"), "upgrade", "head"])


def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1" if host in ("0.0.0.0", "") else host, port))
            return True
        except OSError:
            return False


def wait_health(url: str, timeout: float = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    return False


def serve(cfg: dict, args: argparse.Namespace, pm: list[str] | None) -> None:
    host = args.host or cfg["host"]
    port = args.port or cfg["port"]
    if not port_free(host, port):
        fail(f"端口 {port} 已被占用", "请关闭占用程序，或在 config.yaml 的 server.port 修改端口，或 python run.py --port 8001")
    env = {**os.environ, "PYTHONUTF8": "1", "PYDANTIC_AI_NO_BANNER": "1"}
    if PW_DIR.is_dir() and "PLAYWRIGHT_BROWSERS_PATH" not in env:
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(PW_DIR)
    procs: list[subprocess.Popen] = []
    kw = {"cwd": str(ROOT), "env": env}
    if IS_WIN:
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    # 注意：不要加 --reload（Windows 上会改用 SelectorEventLoop，导致 Playwright 无法启动浏览器）
    procs.append(subprocess.Popen([str(VENV_PY), "-m", "uvicorn", "cloudsearch.app:app", "--host", host,
                                   "--port", str(port)], **kw))
    if not cfg["embedded"]:
        procs.append(subprocess.Popen([str(VENV_PY), "-m", "cloudsearch.worker.main"], **kw))
    if args.dev and pm:
        procs.append(subprocess.Popen(pm + ["run", "dev", "--port", "5173"], cwd=str(WEB),
                                      env={**env, "CS_API_PORT": str(port)}))
    local = f"http://127.0.0.1:{port}"
    step("启动服务")
    if not wait_health(f"{local}/api/health"):
        for p in procs:
            p.terminate()
        fail("服务未能在 60 秒内就绪，请查看上方日志")
    url = "http://127.0.0.1:5173" if args.dev else local
    print(f"\n  云搜浏览器已启动：{url}\n  第一个注册的账号为管理员；按 Ctrl+C 停止。\n", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        info("有进程已退出，正在停止其他进程…")
    except KeyboardInterrupt:
        print("\n正在停止…", flush=True)
    finally:
        for p in procs:
            if p.poll() is None:
                if IS_WIN:
                    p.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                else:
                    p.terminate()
        for p in procs:
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill()


def main() -> None:
    ap = argparse.ArgumentParser(description="云搜浏览器一键启动")
    ap.add_argument("--setup-only", action="store_true", help="只安装/打包/迁移，不启动")
    ap.add_argument("--dev", action="store_true", help="同时启动前端热更新服务（5173）")
    ap.add_argument("--no-install", action="store_true", help="跳过依赖检查")
    ap.add_argument("--no-build", action="store_true", help="跳过前端打包")
    ap.add_argument("--rebuild", action="store_true", help="强制重新安装依赖并打包")
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    ap.add_argument("--host")
    ap.add_argument("--port", type=int)
    args = ap.parse_args()

    os.chdir(ROOT)
    check_python()
    ensure_config()
    opts = install_options()
    pm = None
    if not args.no_install:
        ensure_venv(args.rebuild, opts)
        ensure_chromium(opts)
        pm = ensure_web(args.rebuild, not args.no_build, args.rebuild, opts)
    elif not VENV_PY.exists():
        fail("尚未安装环境，请去掉 --no-install 运行一次")
    elif args.dev:
        pm, _ = node_tools()
    cfg = app_config()
    info(f"数据库：{cfg['db']}；执行器：{'内嵌' if cfg['embedded'] else '独立进程'}")
    migrate(cfg)
    if args.setup_only:
        step("准备完成")
        return
    serve(cfg, args, pm)


if __name__ == "__main__":
    main()
