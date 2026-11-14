"""全局配置。

来源优先级（高 → 低）：环境变量 CS_* > config.yaml > 代码默认值。
- config.yaml 位于仓库根目录（可用环境变量 CS_CONFIG_FILE 指定其他路径），模板见 config.example.yaml
- YAML 按分区书写（database / security / server / browser / search / task / worker / storage / web / llm），
  加载时展开为扁平字段，例如 browser.headless → browser_headless；未知键会直接报错，防止拼写错误被静默忽略
- llm 分区（供应方/模型/智能体绑定）不属于 Settings，由 llm/seed.py 在启动时同步进数据库
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent

# Playwright 浏览器默认安装在仓库根目录 .playwright（启动脚本负责安装）；已显式设置时不覆盖
if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ and (PROJECT_ROOT / ".playwright").is_dir():
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(PROJECT_ROOT / ".playwright")


class ConfigError(ValueError):
    pass


def config_file_path() -> Path:
    p = Path(os.environ.get("CS_CONFIG_FILE", PROJECT_ROOT / "config.yaml"))
    return p if p.is_absolute() else (PROJECT_ROOT / p)


def load_config_file() -> dict[str, Any]:
    """读取 config.yaml 原始内容；文件不存在返回空字典。"""
    p = config_file_path()
    if not p.is_file():
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{p} 不是合法的 YAML：{e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{p} 顶层必须是键值对")
    return data


# YAML 分区键 → Settings 字段名（未列出的按“分区_键”拼接）
_ALIASES: dict[tuple[str, str], str] = {
    ("security", "secret_key"): "secret_key",
    ("security", "master_key"): "master_key",
    ("security", "access_token_minutes"): "access_token_minutes",
    ("security", "allow_registration"): "allow_registration",
    ("database", "auto_create_tables"): "auto_create_tables",
    ("worker", "embedded"): "embedded_worker",
    ("worker", "id"): "worker_id",
    ("storage", "dir"): "storage_dir",
    ("web", "dist_dir"): "web_dist_dir",
    ("app", "env"): "env",
}
_SKIP_SECTIONS = {"llm", "install"}  # llm 由 llm/seed.py 处理；install 由 run.py 读取
_DB_KEYS = {"type", "url", "sqlite_path", "mysql", "auto_create_tables"}


def _rel(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (PROJECT_ROOT / p)


def _database_url(db: dict[str, Any]) -> str | None:
    if db.get("url"):
        return str(db["url"])
    kind = (db.get("type") or "").lower()
    if kind in ("", "sqlite"):
        if "sqlite_path" in db or kind == "sqlite":
            path = _rel(db.get("sqlite_path") or "backend/data/cloudsearch.db")
            return f"sqlite+aiosqlite:///{path.as_posix()}"
        return None
    if kind == "mysql":
        m = db.get("mysql") or {}
        missing = [k for k in ("host", "user", "name") if not m.get(k)]
        if missing:
            raise ConfigError(f"database.mysql 缺少：{', '.join(missing)}")
        pwd = quote_plus(str(m.get("password") or ""))
        user = quote_plus(str(m["user"]))
        charset = m.get("charset", "utf8mb4")
        return f"mysql+asyncmy://{user}:{pwd}@{m['host']}:{int(m.get('port', 3306))}/{m['name']}?charset={charset}"
    raise ConfigError(f"database.type 只能是 sqlite 或 mysql，当前为：{kind}")


def flatten_config(data: dict[str, Any], field_names: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    unknown: list[str] = []
    for section, values in data.items():
        if section in _SKIP_SECTIONS:
            continue
        if not isinstance(values, dict):
            unknown.append(section)
            continue
        if section == "database":
            bad = set(values) - _DB_KEYS
            unknown += [f"database.{k}" for k in bad]
            url = _database_url(values)
            if url:
                out["database_url"] = url
            if "auto_create_tables" in values:
                out["auto_create_tables"] = values["auto_create_tables"]
            continue
        for key, value in values.items():
            name = _ALIASES.get((section, key), f"{section}_{key}")
            if name not in field_names:
                unknown.append(f"{section}.{key}")
                continue
            if value is None:
                continue  # 留空 = 使用默认值
            if name in ("storage_dir", "web_dist_dir"):
                value = _rel(value)
            out[name] = value
    if unknown:
        raise ConfigError(f"{config_file_path().name} 中有无法识别的配置项：{', '.join(sorted(unknown))}"
                          "（请对照 config.example.yaml）")
    return out


class YamlConfigSource(PydanticBaseSettingsSource):
    def get_field_value(self, field, field_name):  # noqa: ANN001  (未使用，按整体返回)
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return flatten_config(load_config_file(), set(self.settings_cls.model_fields))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CS_", env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"),
                                      env_file_encoding="utf-8", extra="ignore")

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings,
                                   file_secret_settings):
        return init_settings, env_settings, dotenv_settings, YamlConfigSource(settings_cls), file_secret_settings

    env: str = "dev"
    # 应用状态库（cloudsearch_app）。生产使用 MySQL 8
    database_url: str = f"sqlite+aiosqlite:///{(BACKEND_ROOT / 'data' / 'cloudsearch.db').as_posix()}"
    # 自动建表（开发方便）；生产建议 false 并使用 alembic upgrade head
    auto_create_tables: bool = True

    # JWT 签名密钥与 API Key 加密主密钥（Fernet）。生产必须显式配置。
    secret_key: str = "dev-only-secret-change-me-in-production-0123456789"
    master_key: str = ""
    access_token_minutes: int = 60 * 24
    allow_registration: bool = True

    # 服务监听（启动脚本使用）
    server_host: str = "127.0.0.1"
    server_port: int = 8000

    # 前端打包产物（存在时由 API 同端口提供页面）
    web_dist_dir: Path = PROJECT_ROOT / "web" / "dist"

    # 私有对象存储（P0 本地目录；S3 兼容存储为后续适配器）
    storage_dir: Path = BACKEND_ROOT / "data" / "storage"

    # 云端浏览器
    browser_headless: bool = True
    # 浏览器内核：auto（已装自带 Chromium 则用，否则用系统 Edge/Chrome）/ bundled / msedge / chrome
    browser_channel: str = "auto"
    browser_executable_path: str | None = None
    browser_proxy: str | None = Field(default_factory=lambda: os.environ.get("HTTPS_PROXY") or None)
    browser_max_contexts: int = 4
    browser_nav_timeout_ms: int = 30000
    browser_frame_interval_s: float = 2.0
    browser_locale: str = "zh-CN"
    # 允许访问私网/环回地址（仅限本地测试，生产必须为 false）
    browser_allow_private_network: bool = False
    # 人工接管：遇到人机验证/登录墙时暂停并请用户在实时画面中处理；超时则按原逻辑（换引擎/标记受限）继续
    browser_takeover_enabled: bool = True
    browser_takeover_timeout_s: int = 300

    # 浏览器搜索：引擎顺序与被拦截后的冷却时间
    search_engines: list[str] = ["duckduckgo", "google", "bing", "baidu", "sogou"]
    # priority：总是优先第一个引擎，失败才换下一个；rotate：轮换起始引擎分散负载
    search_strategy: str = "priority"
    search_engine_cooldown_s: int = 600
    search_unreachable_cooldown_s: int = 300
    # 可供搜索规划选用的垂直来源（None = 全部内置来源）与用户自定义来源（见 search/sources.py SourceConfig）
    search_vertical_sources: list[str] | None = None
    search_custom_sources: list[dict] = []
    search_results_per_query: int = 8

    # 单个任务的上限（模型给出的计划会被截断到这些值以内）
    task_max_sources: int = 12
    task_max_queries: int = 6
    task_read_concurrency: int = 3
    task_max_llm_requests: int = 60
    # 研究类任务“反思→补查”的最多轮数（数据任务最多 1 轮；简答不补查）
    task_max_extra_waves: int = 2

    # 上传文件（对话中的附件）：解析为 Markdown 后作为可引用的来源参与问答与分析
    files_max_mb: int = 100
    files_max_per_message: int = 10
    # 解析器：auto（按 MinerU 自部署 → MinerU 云端 → MinerU 命令行 → 内置 的顺序选可用的）/ builtin /
    # mineru_api / mineru_cloud / mineru_cli / mineru_agent（mineru.net 免登录轻量接口，文件会上传到 mineru.net）
    files_parser: str = "auto"
    files_parse_concurrency: int = 2
    files_parse_timeout_s: int = 1800

    # MinerU 多模态文档解析（PDF/扫描件/图片/Office → Markdown，含表格、公式、版面）
    mineru_api_url: str | None = None  # 自部署服务地址，如 http://127.0.0.1:8003（mineru-kit file-parse-server）
    mineru_api_key: str | None = None  # 自部署服务前若有网关鉴权，填 Bearer token
    mineru_tier: str = "standard"  # flash / basic / standard / advanced（MinerU 4.x）
    mineru_cloud_token: str | None = None  # mineru.net 精准解析 API 的 Token（填写即表示同意把文件发送到 mineru.net）
    mineru_cloud_model: str = "vlm"  # pipeline / vlm
    mineru_language: str = "ch"
    mineru_cli_command: list[str] = ["mineru", "parse", "{input}", "-o", "{output}", "--pages", "all"]

    # worker（embedded=true 时嵌入 API 进程，单进程即可运行；生产建议独立 worker）
    embedded_worker: bool = True
    worker_id: str = Field(default_factory=lambda: f"worker-{os.getpid()}")
    worker_poll_interval_s: float = 1.0
    worker_lease_s: int = 60
    worker_max_tasks: int = 2
    worker_processes: int = 1  # 服务器脚本启动的独立 worker 进程数（embedded=false 时）
    # 独立 worker 的内部实时通道（API 转发实时画面与人工输入）：监听地址与对 API 公布的主机名
    worker_live_bind: str = "127.0.0.1"
    worker_live_advertise_host: str = "127.0.0.1"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    if s.database_url.startswith("sqlite"):
        db_path = s.database_url.split(":///", 1)[-1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return s
