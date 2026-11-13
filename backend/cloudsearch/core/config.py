"""全局配置：全部来自环境变量（前缀 CS_），开发默认值可直接运行。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CS_", env_file=".env", extra="ignore")

    env: str = "dev"
    # 应用状态库（cloudsearch_app）。生产使用 MySQL 8：mysql+asyncmy://user:pwd@host:3306/cloudsearch_app
    database_url: str = f"sqlite+aiosqlite:///{BACKEND_ROOT / 'data' / 'cloudsearch.db'}"
    # 开发期自动建表；生产应关闭并使用 alembic upgrade
    auto_create_tables: bool = True

    # JWT 签名密钥与 API Key 加密主密钥（Fernet，urlsafe base64 32字节）。生产必须显式配置。
    secret_key: str = "dev-only-secret-change-me-in-production-0123456789"
    master_key: str = ""
    access_token_minutes: int = 60 * 24
    allow_registration: bool = True

    # 私有对象存储（P0 本地目录；S3 兼容存储为后续适配器）
    storage_dir: Path = BACKEND_ROOT / "data" / "storage"

    # 云端浏览器
    browser_headless: bool = True
    browser_proxy: str | None = Field(default_factory=lambda: os.environ.get("HTTPS_PROXY") or None)
    browser_max_contexts: int = 4
    browser_nav_timeout_ms: int = 30000
    browser_frame_interval_s: float = 2.0
    browser_locale: str = "zh-CN"
    # 允许访问私网/环回地址（仅限本地测试，生产必须为 False）
    browser_allow_private_network: bool = False

    # 浏览器搜索：引擎顺序与被拦截后的冷却时间
    search_engines: list[str] = ["bing", "baidu", "sogou"]
    search_engine_cooldown_s: int = 600
    search_results_per_query: int = 8

    # 任务执行默认上限（可被 TaskSpec 覆盖为更小值）
    task_max_sources: int = 12
    task_max_queries: int = 6
    task_read_concurrency: int = 3
    task_max_llm_requests: int = 60

    # worker（开发模式下嵌入 API 进程，单命令即可运行；生产建议独立部署 worker）
    embedded_worker: bool = True
    worker_id: str = Field(default_factory=lambda: f"worker-{os.getpid()}")
    worker_poll_interval_s: float = 1.0
    worker_lease_s: int = 60
    worker_max_tasks: int = 2


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    if s.database_url.startswith("sqlite"):
        (BACKEND_ROOT / "data").mkdir(parents=True, exist_ok=True)
    return s
