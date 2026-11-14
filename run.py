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
  python run.py --check-search  诊断各搜索引擎在本机网络下是否可用
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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

# 所有子进程（迁移、服务、worker、pip）统一使用 UTF-8 模式：
# 避免中文 Windows 上第三方库按本地编码（GBK）读取 UTF-8 文件出错
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

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
        return
    upgrade_config(cfg)


# 早期模板中的默认值 → 新默认值。只替换“原样未改动”的旧默认行，并先备份。
_CONFIG_UPGRADES = [
    (re.compile(r"^(?P<indent>[ \t]+)engines:[ \t]*\[[ \t]*bing[ \t]*,[ \t]*baidu[ \t]*,[ \t]*sogou[ \t]*\][^\n]*$", re.M),
     "{indent}engines: [duckduckgo, google, bing, baidu, sogou]  # 已自动升级（原为 [bing, baidu, sogou]）",
     "search.engines 从旧默认 [bing, baidu, sogou] 升级为 [duckduckgo, google, bing, baidu, sogou]"),
]


def upgrade_config(cfg: Path) -> None:
    text = cfg.read_text(encoding="utf-8")
    new, notes = text, []
    for pattern, repl, note in _CONFIG_UPGRADES:
        new, n = pattern.subn(lambda m, r=repl: r.format(indent=m.group("indent")), new)
        if n:
            notes.append(note)
    if not notes:
        return
    backup = cfg.with_name(f"config.yaml.bak-{time.strftime('%Y%m%d%H%M%S')}")
    shutil.copy(cfg, backup)
    cfg.write_text(new, encoding="utf-8")
    step("已升级 config.yaml 中未改动过的旧默认值")
    for n in notes:
        info(n)
    info(f"原文件已备份为 {backup.name}；如需保留旧设置，把对应行改回即可")


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
            "'auto_create':s.auto_create_tables,'db':s.database_url.split(':',1)[0],"
            "'mineru_local':s.mineru_local,'mineru_port':s.mineru_local_port,'mineru_tier':s.mineru_tier,"
            "'mineru_source':s.mineru_model_source,'mineru_extras':s.mineru_extras,"
            "'ollama_url':s.local_llm_ollama_url,'ollama_models':s.local_llm_ollama_models,"
            "'local_only':s.privacy_data_local_only}))")
    try:
        out = subprocess.check_output([str(VENV_PY), "-c", code], cwd=str(ROOT), text=True, stderr=subprocess.STDOUT,
                                      encoding="utf-8")
    except subprocess.CalledProcessError as e:
        fail("config.yaml 配置有误：\n" + e.output.strip().splitlines()[-1])
    return json.loads(out.strip().splitlines()[-1])


# ------------------------------------------------------------------ 本机 AI 组件（数据不出域）
# MinerU 装在独立环境 .venv-mineru（依赖较重，与主程序隔离），模型放在 .mineru/models，运行时离线加载
MINERU_VENV = ROOT / ".venv-mineru"
MINERU_HOME = ROOT / ".mineru"
MINERU_PY = MINERU_VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")
MINERU_KIT = MINERU_VENV / ("Scripts/mineru-kit.exe" if IS_WIN else "bin/mineru-kit")
MODEL_DOWNLOAD_TIMEOUT_S = 3 * 3600


def mineru_env(offline: bool) -> dict[str, str]:
    env = {"MINERU_HOME": str(MINERU_HOME), "PYTHONUTF8": "1"}
    if offline:
        env["MINERU_MODEL_SOURCE"] = "local"  # 只用已下载的模型，缺失时报错而不是联网下载
    return env


def mineru_model_tier(tier: str) -> str | None:
    """下载哪一档模型：flash 不需要模型；advanced 与 standard 共用模型。"""
    return None if tier == "flash" else ("standard" if tier in ("standard", "advanced") else "basic")


def ensure_mineru(cfg: dict, opts: dict[str, list[str]], force: bool) -> None:
    if not cfg.get("mineru_local"):
        return
    step("准备 MinerU（本机文档解析：安装到 .venv-mineru，模型保存在 .mineru/）")
    extras = (cfg.get("mineru_extras") or "").strip()
    spec = f"mineru[{extras}]>=4.0,<5" if extras else "mineru>=4.0,<5"
    stamp = MINERU_VENV / ".cloudsearch-mineru"
    if force or not MINERU_KIT.exists() or not stamp_ok(stamp, spec):
        uv = shutil.which("uv")
        if not MINERU_PY.exists():
            if uv:
                run([uv, "venv", str(MINERU_VENV), "--python", sys.executable, "--seed"])
            else:
                run([sys.executable, "-m", "venv", str(MINERU_VENV)])
        sources = order_sources("Python 包", PIP_SOURCES, opts.get("pip_index_urls", []), "/pip/")

        def attempt(index: str) -> bool:
            if uv:
                env = {"UV_HTTP_TIMEOUT": "120", "UV_CONCURRENT_DOWNLOADS": "8", "UV_LINK_MODE": "copy"}
                return run_try([uv, "pip", "install", "--python", str(MINERU_PY), "--index-url", index, spec], env=env)
            return run_try([MINERU_PY, "-m", "pip", "install", "--disable-pip-version-check", "--timeout", "60",
                            "-i", index, "--trusted-host", index.split("/")[2], spec])

        try_sources("安装 MinerU", sources, attempt)
        stamp.write_text(spec, encoding="utf-8")
    else:
        info("MinerU 已安装，跳过")
    tier = mineru_model_tier(cfg.get("mineru_tier") or "standard")
    if tier is None:
        info("tier=flash：不需要下载模型")
        return
    first = cfg.get("mineru_source") or "modelscope"
    order = [first] + [x for x in ("modelscope", "huggingface") if x != first]
    mstamp = MINERU_HOME / f".models-{tier}"
    if mstamp.exists() and not force:
        info(f"MinerU 模型（{tier}）已下载，跳过")
        return
    MINERU_HOME.mkdir(parents=True, exist_ok=True)
    info(f"下载 MinerU 模型（{tier}，首次需要较长时间，之后离线使用）")
    for src in order:
        env = mineru_env(offline=False)
        if src == "huggingface" and "HF_ENDPOINT" not in os.environ:
            env["HF_ENDPOINT"] = (opts.get("hf_endpoint") or ["https://hf-mirror.com"])[0]
        if run_try([MINERU_KIT, "models", "download", "--tier", tier, "--source", src], env=env,
                   timeout=MODEL_DOWNLOAD_TIMEOUT_S):
            run_try([MINERU_KIT, "models", "verify", "--tier", tier], env=env, timeout=600)
            mstamp.write_text(src, encoding="utf-8")
            return
        info(f"从 {src} 下载失败，尝试下一个来源…")
    fail("MinerU 模型下载失败", "请检查网络；或把 config.yaml 的 mineru.tier 改为 basic（模型更小），"
         "或暂时关闭 mineru.local（文字版 PDF/Word/Excel 仍可用内置解析）")


def _ollama_bin() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    if IS_WIN:
        p = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if p.exists():
            return str(p)
    return None


def _ollama_tags(url: str) -> list[str] | None:
    try:
        with _LOCAL_OPENER.open(url.rstrip("/") + "/api/tags", timeout=5) as r:
            return [m.get("name", "") for m in json.loads(r.read().decode("utf-8")).get("models", [])]
    except Exception:  # noqa: BLE001
        return None


def ensure_ollama(cfg: dict) -> subprocess.Popen | None:
    """本地大模型：确保 Ollama 在运行，并拉取 config.yaml 的 local_llm.ollama_models。返回本脚本启动的 ollama 进程。"""
    models = cfg.get("ollama_models") or []
    if not models:
        return None
    step("准备本地大模型（Ollama）")
    url = cfg.get("ollama_url") or "http://127.0.0.1:11434"
    exe = _ollama_bin()
    started = None
    tags = _ollama_tags(url)
    if tags is None:
        if not exe:
            info("没有找到 Ollama。请先安装：Windows 从 https://ollama.com/download 下载安装包；"
                 "Linux 运行 curl -fsSL https://ollama.com/install.sh | sh 。安装后重新启动本程序。")
            info("（本次继续启动，但本地大模型不可用）")
            return None
        info("启动 Ollama 服务")
        kw: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if IS_WIN:
            kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        started = subprocess.Popen([exe, "serve"], **kw)
        for _ in range(30):
            time.sleep(1)
            tags = _ollama_tags(url)
            if tags is not None:
                break
        if tags is None:
            info("Ollama 未能启动，本地大模型不可用")
            return started
    for m in models:
        want = m if ":" in m else m + ":latest"
        if want in tags or m in tags:
            info(f"{m} 已存在，跳过")
            continue
        if not exe:
            info(f"需要拉取 {m}，但本机没有 ollama 命令（服务可能在其他机器上），请在 Ollama 所在机器执行 ollama pull {m}")
            continue
        info(f"拉取本地模型 {m}（首次较慢）")
        if not run_try([exe, "pull", m], timeout=MODEL_DOWNLOAD_TIMEOUT_S):
            info(f"拉取 {m} 失败，可稍后手动执行：ollama pull {m}")
    return started


def start_mineru(cfg: dict) -> subprocess.Popen | None:
    """启动本机 MinerU 服务（离线模型），等待端口就绪。失败时不阻止主程序启动（文字版文档仍可内置解析）。"""
    if not cfg.get("mineru_local"):
        return None
    if not MINERU_KIT.exists():
        info("MinerU 尚未安装（去掉 --no-install 运行一次），本次不启动")
        return None
    port = int(cfg.get("mineru_port") or 8002)
    if not port_free("127.0.0.1", port):
        info(f"端口 {port} 已被占用，假定 MinerU 已在运行")
        return None
    MINERU_HOME.mkdir(parents=True, exist_ok=True)
    log = open(MINERU_HOME / "server.log", "ab")  # noqa: SIM115 —— 随进程生命周期
    kw: dict = {"cwd": str(ROOT), "env": {**os.environ, **mineru_env(offline=True)}, "stdout": log, "stderr": log}
    if IS_WIN:
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    tier = cfg.get("mineru_tier") or "standard"
    p = subprocess.Popen([str(MINERU_KIT), "api-server", "--host", "127.0.0.1", "--port", str(port),
                          "--tier", tier], **kw)
    step(f"启动 MinerU（127.0.0.1:{port}，{tier}，离线模型；日志 .mineru/server.log）")
    import socket

    for _ in range(600):
        if p.poll() is not None:
            info(f"MinerU 启动失败（退出码 {p.returncode}），请查看 .mineru/server.log；扫描件/图片/PPT 将无法识别")
            return None
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                info("MinerU 已就绪")
                return p
        except OSError:
            time.sleep(1)
    info("MinerU 10 分钟内未就绪，继续启动主程序（MinerU 就绪后自动可用）")
    return p


def migrate(cfg: dict) -> None:
    step("数据库迁移")
    # 自动识别早期直接建表的库；已是最新时不做任何改动
    run([VENV_PY, "-m", "cloudsearch.db.migrate"])


def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1" if host in ("0.0.0.0", "") else host, port))
            return True
        except OSError:
            return False


# 访问本机服务时不走代理：Windows 上 urllib 会读取系统代理（如 Clash 127.0.0.1:7890），
# 请求 127.0.0.1 也可能被转给代理而失败
_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def wait_health(url: str, timeout: float = 60, procs: list | None = None) -> tuple[bool, str]:
    """轮询健康检查；返回 (是否就绪, 最后一次失败原因)。服务进程退出时立即返回。"""
    deadline = time.time() + timeout
    last = "尚未响应"
    while time.time() < deadline:
        if procs and procs[0].poll() is not None:
            return False, f"服务进程已退出（退出码 {procs[0].returncode}）"
        try:
            with _LOCAL_OPENER.open(url, timeout=10) as r:
                if r.status == 200:
                    return True, ""
                last = f"HTTP {r.status}"
        except urllib.error.HTTPError as e:
            body = e.read()[:200].decode("utf-8", "replace")
            last = f"HTTP {e.code} {body}"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"[:200]
        time.sleep(1)
    return False, last


def serve(cfg: dict, args: argparse.Namespace, pm: list[str] | None,
          extra: list[subprocess.Popen] | None = None) -> None:
    host = args.host or cfg["host"]
    port = args.port or cfg["port"]
    if not port_free(host, port):
        fail(f"端口 {port} 已被占用", "请关闭占用程序，或在 config.yaml 的 server.port 修改端口，或 python run.py --port 8001")
    if cfg.get("mineru_local") and int(cfg.get("mineru_port") or 8002) == int(port):
        fail(f"MinerU 与主程序端口冲突（{port}）", "请修改 config.yaml 的 mineru.local_port")
    env = {**os.environ, "PYTHONUTF8": "1", "PYDANTIC_AI_NO_BANNER": "1"}
    if PW_DIR.is_dir() and "PLAYWRIGHT_BROWSERS_PATH" not in env:
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(PW_DIR)
    procs: list[subprocess.Popen] = []
    helpers = [p for p in (extra or []) if p is not None]  # MinerU / Ollama：随主程序一起停止
    kw = {"cwd": str(ROOT), "env": env}
    if IS_WIN:
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    # 用 cloudsearch.serve 启动（自建事件循环，兼容 PyCharm 调试模式；不使用 --reload，
    # 否则 Windows 上会改用 SelectorEventLoop，Playwright 无法启动浏览器）
    procs.append(subprocess.Popen([str(VENV_PY), "-m", "cloudsearch.serve", "--host", host, "--port", str(port)],
                                  **kw))
    if not cfg["embedded"]:
        procs.append(subprocess.Popen([str(VENV_PY), "-m", "cloudsearch.worker.main"], **kw))
    if args.dev and pm:
        procs.append(subprocess.Popen(pm + ["run", "dev", "--port", "5173"], cwd=str(WEB),
                                      env={**env, "CS_API_PORT": str(port)}))
    local = f"http://127.0.0.1:{port}"
    step("启动服务")
    debugging = "pydevd" in sys.modules
    if debugging:
        info("检测到 PyCharm 调试模式：子进程也会被调试器接管，启动和运行较慢；日常使用建议用 Run 或 start.bat")
    wait_s = 180 if debugging else 90
    ok, why = wait_health(f"{local}/api/health", wait_s, procs)
    if not ok:
        if procs[0].poll() is not None:  # 服务确实没起来
            for p in procs:
                p.terminate()
            fail(f"服务启动失败：{why}", "请查看上方日志")
        # 进程还在运行，只是健康检查没通过（常见于代理、杀毒软件拦截本机访问或调试器过慢）：不终止服务
        info(f"健康检查 {wait_s} 秒内未通过（最后一次：{why}），服务进程仍在运行，继续。"
             f"如果浏览器打不开 {local}，请检查系统代理是否对 127.0.0.1 生效，或查看上方日志")
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
        for p in procs + helpers:
            if p.poll() is None:
                if IS_WIN:
                    p.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                else:
                    p.terminate()
        for p in procs + helpers:
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
    ap.add_argument("--check-search", action="store_true", help="诊断各搜索引擎在本机网络下是否可用")
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
    if args.check_search:
        step("搜索引擎诊断")
        sys.exit(subprocess.call([str(VENV_PY), "-m", "cloudsearch.search.diagnose"], cwd=str(ROOT)))
    cfg = app_config()
    info(f"数据库：{cfg['db']}；执行器：{'内嵌' if cfg['embedded'] else '独立进程'}")
    if cfg.get("local_only"):
        info("数据不出域：已开启（大模型与文件解析只使用本机/内网服务）")
    ollama_p = None
    if not args.no_install:
        ensure_mineru(cfg, opts, args.rebuild)
    ollama_p = ensure_ollama(cfg)
    migrate(cfg)
    if args.setup_only:
        if ollama_p is not None and ollama_p.poll() is None:
            ollama_p.terminate()
        step("准备完成")
        return
    mineru_p = start_mineru(cfg)
    serve(cfg, args, pm, extra=[ollama_p, mineru_p])


if __name__ == "__main__":
    main()
