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
import urllib.error
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


# ------------------------------------------------------------------ 多下载源（自动测速，失败/超时自动换下一个）
PIP_SOURCES = [
    ("官方 PyPI", "https://pypi.org/simple"),
    ("清华大学", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    ("阿里云", "https://mirrors.aliyun.com/pypi/simple"),
    ("腾讯云", "https://mirrors.cloud.tencent.com/pypi/simple"),
    ("华为云", "https://repo.huaweicloud.com/repository/pypi/simple"),
]
NPM_SOURCES = [
    ("官方 npm", "https://registry.npmjs.org"),
    ("阿里云 npmmirror", "https://registry.npmmirror.com"),
    ("腾讯云", "https://mirrors.cloud.tencent.com/npm"),
    ("华为云", "https://repo.huaweicloud.com/repository/npm"),
]
# Chromium：清华/腾讯没有镜像 Playwright 浏览器包
PW_SOURCES = [
    ("官方", "https://cdn.playwright.dev"),
    ("阿里云 npmmirror", "https://cdn.npmmirror.com/binaries/playwright"),
    ("华为云", "https://mirrors.huaweicloud.com/playwright"),
]
INSTALL_TIMEOUT_S = 30 * 60  # 单个源的整体安装超时


def install_options() -> dict[str, list[str]]:
    """读取 config.yaml 的 install 分区（无需 yaml 库）。支持：key: url / key: [a, b] / key: 换行 - a。"""
    opts: dict[str, list[str]] = {}
    cfg = ROOT / "config.yaml"
    if not cfg.exists():
        return opts
    in_section, current = False, None
    for raw in cfg.read_text(encoding="utf-8").splitlines():
        line = raw.split(" #", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        if not raw.startswith((" ", "\t")):
            in_section, current = line.strip() == "install:", None
            continue
        if not in_section:
            continue
        item = line.strip()
        if item.startswith("- ") and current:
            opts.setdefault(current, []).append(item[2:].strip().strip("'\""))
            continue
        if ":" in item:
            k, v = item.split(":", 1)
            current, v = k.strip(), v.strip()
            if v.startswith("[") and v.endswith("]"):
                opts[current] = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
            elif v:
                opts[current] = [v.strip("'\"")]
    # 兼容单数写法
    for single, plural in (("pip_index_url", "pip_index_urls"), ("npm_registry", "npm_registries"),
                           ("playwright_download_host", "playwright_download_hosts")):
        if single in opts:
            opts.setdefault(plural, []).extend(opts.pop(single))
    return opts


def _probe(url: str, timeout: float = 5.0) -> float | None:
    """测连通与延迟：能收到任何 HTTP 响应即视为可达。"""
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "cloudsearch-installer"})
        urllib.request.urlopen(req, timeout=timeout).close()
    except urllib.error.HTTPError:
        pass  # 4xx/5xx 也说明网络可达
    except Exception:  # noqa: BLE001
        return None
    return time.monotonic() - t0


def order_sources(kind: str, defaults: list[tuple[str, str]], configured: list[str], probe_path: str = "") \
        -> list[tuple[str, str]]:
    """config.yaml 指定了源则按指定顺序；否则并发测速，从快到慢排列（不可达的放最后仍会尝试）。"""
    if configured:
        names = {u.rstrip("/"): n for n, u in defaults}
        return [(names.get(u.rstrip("/"), "自定义"), u.rstrip("/")) for u in configured]
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(len(defaults)) as ex:
        lat = list(ex.map(lambda s: _probe(s[1] + probe_path), defaults))
    ranked = sorted(zip(defaults, lat), key=lambda x: (x[1] is None, x[1] or 0))
    desc = "，".join(f"{n} {'%.0fms' % (t * 1000) if t is not None else '不可达'}" for (n, _), t in ranked)
    info(f"{kind}下载源测速：{desc}")
    return [s for s, _ in ranked]


def run_try(cmd: list, *, cwd: Path = ROOT, env: dict | None = None, timeout: float = INSTALL_TIMEOUT_S) -> bool:
    """执行命令，失败或超时返回 False（超时会结束整个进程树）。"""
    info("$ " + " ".join(str(c) for c in cmd))
    kw: dict = {"cwd": str(cwd), "env": {**os.environ, **(env or {})}}
    if IS_WIN:
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kw["start_new_session"] = True
    p = subprocess.Popen([str(c) for c in cmd], **kw)
    try:
        return p.wait(timeout=timeout) == 0
    except KeyboardInterrupt:
        _kill_tree(p)
        raise
    except subprocess.TimeoutExpired:
        info(f"超过 {int(timeout // 60)} 分钟未完成，终止")
        _kill_tree(p)
        return False


def _kill_tree(p: subprocess.Popen) -> None:
    if IS_WIN:
        subprocess.call(["taskkill", "/T", "/F", "/PID", str(p.pid)], stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            p.kill()
    p.wait()


def try_sources(kind: str, sources: list[tuple[str, str]], attempt) -> None:
    for i, (name, url) in enumerate(sources):
        info(f"[{i + 1}/{len(sources)}] 使用 {name}：{url}")
        if attempt(url):
            return
        if i + 1 < len(sources):
            info(f"{name} 下载失败，改用下一个源…")
    fail(f"{kind}：所有下载源都失败了", "请检查网络/代理；或在 config.yaml 的 install 分区指定可用的源后重试")


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


def ensure_venv(force: bool, opts: dict[str, list[str]]) -> None:
    """依赖版本与文件哈希锁定在 requirements.txt（由 uv.lock 导出），因此可以安全地从任一镜像下载。"""
    step("准备 Python 环境（仓库根目录 .venv）")
    req = ROOT / "requirements.txt"
    want = file_hash(ROOT / "pyproject.toml", req)
    stamp = VENV / ".cloudsearch-deps"
    if not force and VENV_PY.exists() and stamp_ok(stamp, want):
        info("依赖已是最新，跳过")
        return
    uv = shutil.which("uv")
    if not VENV_PY.exists():
        if uv:
            run([uv, "venv", str(VENV), "--python", sys.executable, "--seed"])
        else:
            run([sys.executable, "-m", "venv", str(VENV)])
    sources = order_sources("Python 包", PIP_SOURCES, opts.get("pip_index_urls", []), "/pip/")

    def attempt(index: str) -> bool:
        host = index.split("/")[2]
        if uv:
            # UV_LINK_MODE=copy：uv 缓存与项目不在同一磁盘（如 C: 与 D:）时无法硬链接，直接复制且不再告警
            env = {"UV_HTTP_TIMEOUT": "60", "UV_CONCURRENT_DOWNLOADS": "8", "UV_LINK_MODE": "copy"}
            base = [uv, "pip", "install", "--python", str(VENV_PY), "--index-url", index]
            return (run_try(base + ["--require-hashes", "-r", str(req)], env=env)
                    and run_try(base + ["--no-deps", "-e", "."], env=env))
        base = [VENV_PY, "-m", "pip", "install", "--disable-pip-version-check", "--timeout", "30", "--retries", "2",
                "-i", index, "--trusted-host", host]
        # 本项目以可编辑方式安装（构建工具 hatchling 也从同一个源获取）
        return run_try(base + ["--require-hashes", "-r", str(req)]) and run_try(base + ["--no-deps", "-e", "."])

    try_sources("安装 Python 依赖", sources, attempt)
    stamp.write_text(want, encoding="utf-8")


def browser_choice() -> dict:
    out = subprocess.check_output([str(VENV_PY), "-m", "cloudsearch.browser.launch"], cwd=str(ROOT), text=True,
                                  encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    return json.loads(out.strip().splitlines()[-1])


def ensure_chromium(opts: dict[str, list[str]]) -> None:
    step("准备云端浏览器")
    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(PW_DIR)
    choice = browser_choice()
    if choice["mode"] == "error":
        fail(choice["detail"])
    if choice["mode"] != "missing":
        info(f"使用：{choice['detail']}（无需下载）")
        return
    info("未找到可用浏览器，下载 Playwright 自带 Chromium（约 200MB）")
    sources = order_sources("Chromium ", PW_SOURCES, opts.get("playwright_download_hosts", []))
    cmd = [VENV_PY, "-m", "playwright", "install", "chromium"]
    if not IS_WIN and sys.platform != "darwin" and hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd.append("--with-deps")  # Linux root：顺带安装系统依赖库

    def attempt(host: str) -> bool:
        # 20 秒无数据即判定卡住，换下一个源（避免停在 0%）
        return run_try(cmd, env={"PLAYWRIGHT_DOWNLOAD_HOST": host, "PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT": "20000"},
                       timeout=20 * 60)

    try_sources("下载 Chromium", sources, attempt)


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


def ensure_web(force_install: bool, build: bool, force_build: bool, opts: dict[str, list[str]]) -> list[str]:
    step("准备前端（Vue 3）")
    pm, kind = node_tools()
    want = file_hash(WEB / "package.json", WEB / "pnpm-lock.yaml")
    stamp = WEB / "node_modules" / ".cloudsearch-deps"
    if force_install or not stamp_ok(stamp, want):
        sources = order_sources("前端包", NPM_SOURCES, opts.get("npm_registries", []), "/vue")

        def attempt(registry: str) -> bool:
            env = {"npm_config_registry": registry, "npm_config_fetch_timeout": "60000",
                   "npm_config_fetch_retries": "2", "COREPACK_NPM_REGISTRY": registry}
            if kind == "pnpm":
                return run_try(pm + ["install", "--frozen-lockfile"], cwd=WEB, env=env)
            info("未检测到 pnpm/corepack，改用 npm 安装（不使用锁文件）")
            return run_try(pm + ["install"], cwd=WEB, env=env)

        try_sources("安装前端依赖", sources, attempt)
        stamp.write_text(want, encoding="utf-8")
    else:
        info("前端依赖已是最新，跳过")
    if build:
        index = WEB / "dist" / "index.html"
        sources_files = [WEB / "index.html", WEB / "package.json", WEB / "vite.config.ts", *(WEB / "src").rglob("*")]
        newest = max(p.stat().st_mtime for p in sources_files if p.is_file())
        if force_build or not index.exists() or index.stat().st_mtime < newest:
            step("打包前端")
            run(pm + ["run", "build"], cwd=WEB)
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
