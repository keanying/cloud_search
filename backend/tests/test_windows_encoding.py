"""中文 Windows（本地编码 GBK）兼容。

在 Linux 上用 localedef 生成真实的 zh_CN.GBK 区域设置并关闭 UTF-8 模式，复现“第三方库按本地编码读取 UTF-8 文件”的问题。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def gbk_env(tmp_path_factory):
    if sys.platform == "win32":
        pytest.skip("Windows 上由真实环境覆盖")
    if not shutil.which("localedef"):
        pytest.skip("缺少 localedef，无法生成 GBK 区域设置")
    locdir = tmp_path_factory.mktemp("locale")
    r = subprocess.run(["localedef", "-i", "zh_CN", "-f", "GBK", str(locdir / "zh_CN.GBK")], capture_output=True)
    if not (locdir / "zh_CN.GBK").exists():
        pytest.skip(f"无法生成 GBK 区域设置：{r.stderr[-200:]!r}")
    env = {**os.environ, "LOCPATH": str(locdir), "LC_ALL": "zh_CN.GBK", "PYTHONUTF8": "0"}
    check = subprocess.run([sys.executable, "-X", "utf8=0", "-c", "import locale;print(locale.getencoding())"],
                           env=env, capture_output=True, text=True)
    if check.stdout.strip().upper() != "GBK":
        pytest.skip("GBK 区域设置未生效")
    return env


def _run(code: str, env: dict, tmp_path: Path) -> subprocess.CompletedProcess:
    env = {**env, "CS_CONFIG_FILE": str(tmp_path / "none.yaml"),
           "CS_DATABASE_URL": f"sqlite+aiosqlite:///{(tmp_path / 'g.db').as_posix()}"}
    return subprocess.run([sys.executable, "-X", "utf8=0", "-c", code], env=env, capture_output=True,
                          cwd=str(ROOT))


def test_files_read_with_locale_encoding_are_ascii():
    for rel in ("backend/alembic.ini", "backend/migrations/script.py.mako"):
        assert (ROOT / rel).read_bytes().isascii(), f"{rel} 含非 ASCII 字符，中文 Windows 上会按 GBK 读取失败"


def test_non_ascii_ini_fails_under_gbk(gbk_env, tmp_path):
    """对照：复现用户遇到的错误——含中文的 ini 被 alembic 按 GBK 读取。"""
    ini = tmp_path / "a.ini"
    ini.write_text("[alembic]\n# sqlalchemy.url 由 migrations/env.py 从 CS_DATABASE_URL 读取\nscript_location = x\n",
                   encoding="utf-8")
    r = _run(f"from alembic.config import Config; Config(r'{ini}').get_main_option('script_location')", gbk_env,
             tmp_path)
    assert r.returncode != 0 and b"UnicodeDecodeError" in r.stderr


def test_auto_migrate_under_gbk_without_utf8_mode(gbk_env, tmp_path):
    """即使没有 PYTHONUTF8（例如直接在 PyCharm 里运行迁移模块），自动迁移也能成功。"""
    r = _run("import runpy, sys; sys.argv=['m']; runpy.run_module('cloudsearch.db.migrate', run_name='__main__')",
             gbk_env, tmp_path)
    assert r.returncode == 0, r.stderr.decode("gbk", "replace")[-1500:]


def test_alembic_cli_with_project_ini_under_gbk(gbk_env, tmp_path):
    """服务器上手动执行 alembic 命令时，项目 alembic.ini 也能被读取。"""
    r = _run("import sys; from alembic.config import main; "
             "main(argv=['-c', 'backend/alembic.ini', 'upgrade', 'head'])", gbk_env, tmp_path)
    assert r.returncode == 0, r.stderr.decode("gbk", "replace")[-1500:]
