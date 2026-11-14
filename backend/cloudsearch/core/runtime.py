"""运行参数：管理后台可在线修改的配置项（覆盖 config.yaml 中的同名项，无需重启）。

- 覆盖值存放在 src_opr_system_setting_f 表；
- 每个进程（API、worker）定期（TTL）把覆盖值写到内存中的 Settings 对象上，新任务即按新参数执行；
- 删除覆盖值即恢复 config.yaml（或默认值）。
只开放“调了就能立即生效、且不涉及密钥/连接”的项；数据库、端口、浏览器内核等仍在 config.yaml 中修改并重启。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from .config import get_settings

ENGINE_LABELS = {"duckduckgo": "DuckDuckGo", "bing": "必应 Bing", "baidu": "百度", "sogou": "搜狗"}


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    group: str  # search / task / browser
    type: str  # engine_order / select / multi / int / bool
    help: str
    min: int | None = None
    max: int | None = None


FIELDS: list[Field] = [
    Field("search_engines", "通用搜索引擎（按优先级）", "search", "engine_order",
          "勾选要使用的引擎并调整顺序。priority 策略下总是先用第一个可用引擎，失败、被拦截或结果无关时再换下一个。"),
    Field("search_strategy", "引擎使用策略", "search", "select",
          "priority：按顺序优先；rotate：每个查询轮换起始引擎，分散单个引擎的压力。"),
    Field("search_vertical_sources", "可用的垂直来源", "search", "multi",
          "搜索规划智能体可以按需选用这些专门来源（百科、论文、公众号等）。全部取消则只用通用引擎。"),
    Field("search_results_per_query", "每个查询取结果数", "search", "int",
          "每次搜索从结果页读取的条数。越多候选越全，但筛选更慢。", 3, 20),
    Field("search_engine_cooldown_s", "被拦截后冷却（秒）", "search", "int",
          "引擎要求人机验证且未处理时，暂停使用该引擎的时长。", 60, 7200),
    Field("search_unreachable_cooldown_s", "无法访问后冷却（秒）", "search", "int",
          "引擎网络不通或拒绝访问时，暂停使用该引擎的时长。", 30, 7200),
    Field("task_max_sources", "每个任务最多读取网页", "task", "int",
          "需求编译给出的上限不会超过此值的默认设定；越多越全面，耗时和费用也越高。", 1, 40),
    Field("task_max_queries", "每个任务最多搜索次数", "task", "int", "首轮搜索的查询词数量上限。", 1, 20),
    Field("task_read_concurrency", "同时打开网页数", "task", "int",
          "每个任务并行读取网页的数量。调高更快，但更容易触发网站风控。", 1, 8),
    Field("task_max_llm_requests", "每个任务最多模型调用", "task", "int",
          "单个任务允许的模型调用总次数，防止异常任务消耗过多费用。", 10, 400),
    Field("task_max_extra_waves", "研究任务补查轮数", "task", "int",
          "深入研究时，按子问题评估覆盖度后针对缺口补充搜索的最多轮数。0 表示不补查。", 0, 4),
    Field("browser_takeover_enabled", "人机验证时请求人工接手", "browser", "bool",
          "遇到验证码/人机验证时暂停任务，在实时画面中请用户完成验证；关闭则直接跳过该网站。"),
    Field("browser_takeover_timeout_s", "等待接手时长（秒）", "browser", "int",
          "超过这个时间无人处理，就跳过该网站继续任务。", 60, 1800),
]
BY_KEY = {f.key: f for f in FIELDS}

_base: dict[str, Any] = {}  # 首次覆盖前 config.yaml 的原值
_base_owner: int | None = None  # 对应的 Settings 对象（重新加载配置后重新记录）
_loaded_at = 0.0
TTL_S = 10.0


def _engines() -> tuple[list[str], list[tuple[str, str]]]:
    """(通用引擎名列表, [(垂直来源名, 中文名)])"""
    from ..search.service import all_engines

    general, vertical = [], []
    for name, e in all_engines().items():
        cfg = getattr(e, "cfg", None)
        if cfg is not None and cfg.kind == "vertical":
            vertical.append((name, cfg.label))
        else:
            general.append(name)
    return general, vertical


def engine_label(name: str) -> str:
    from ..search.service import all_engines

    e = all_engines().get(name)
    cfg = getattr(e, "cfg", None)
    return cfg.label if cfg is not None else ENGINE_LABELS.get(name, name)


def options_for(f: Field) -> list[dict] | None:
    if f.key == "search_engines":
        return [{"value": n, "label": engine_label(n)} for n in _engines()[0]]
    if f.key == "search_strategy":
        return [{"value": "priority", "label": "按顺序优先"}, {"value": "rotate", "label": "轮换"}]
    if f.key == "search_vertical_sources":
        return [{"value": n, "label": lab} for n, lab in _engines()[1]]
    return None


def validate(key: str, value: Any) -> Any:
    """校验并规范化；不合法时抛 ValueError（中文说明）。"""
    f = BY_KEY.get(key)
    if f is None:
        raise ValueError(f"不支持在线修改的参数：{key}")
    if f.type == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{f.label}：需要开/关")
        return value
    if f.type == "int":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
            raise ValueError(f"{f.label}：需要整数")
        v = int(value)
        if (f.min is not None and v < f.min) or (f.max is not None and v > f.max):
            raise ValueError(f"{f.label}：取值范围 {f.min}–{f.max}")
        return v
    allowed = {o["value"] for o in options_for(f) or []}
    if f.type == "select":
        if value not in allowed:
            raise ValueError(f"{f.label}：可选值为 {', '.join(sorted(allowed))}")
        return value
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{f.label}：需要名称列表")
    v = list(dict.fromkeys(value))
    bad = [x for x in v if x not in allowed]
    if bad:
        raise ValueError(f"{f.label}：未知的引擎/来源 {', '.join(bad)}")
    if f.type == "engine_order" and not v:
        raise ValueError(f"{f.label}：至少保留一个搜索引擎")
    return v


def _remember_base() -> None:
    global _base_owner
    s = get_settings()
    if _base_owner != id(s):
        _base.clear()
        _base_owner = id(s)
    for f in FIELDS:
        _base.setdefault(f.key, getattr(s, f.key))


def base_value(key: str) -> Any:
    _remember_base()
    return _base[key]


def apply(values: dict[str, Any]) -> None:
    """把覆盖值写到当前进程的 Settings 上；未覆盖的项恢复为 config.yaml 原值。"""
    _remember_base()
    s = get_settings()
    for f in FIELDS:
        v = values.get(f.key, _base[f.key])
        try:
            v = validate(f.key, v) if f.key in values else v
        except ValueError:
            v = _base[f.key]  # 库里的旧值已不合法（如自定义来源被删），回退到配置文件
        object.__setattr__(s, f.key, v)


async def load_overrides(session=None) -> dict[str, Any]:
    from ..db.base import session_scope
    from ..db.models import SystemSetting

    async def read(s) -> dict[str, Any]:
        rows = (await s.execute(select(SystemSetting))).scalars().all()
        return {r.setting_key: r.setting_value for r in rows if r.setting_key in BY_KEY}

    if session is not None:
        return await read(session)
    async with session_scope() as s:
        return await read(s)


async def refresh(*, force: bool = False) -> None:
    """按 TTL 从数据库刷新覆盖值（worker 每轮领取任务前、API 启动时调用）。"""
    global _loaded_at
    if not force and time.monotonic() - _loaded_at < TTL_S:
        return
    try:
        values = await load_overrides()
    except Exception:  # noqa: BLE001 —— 表尚未迁移等情况：沿用配置文件
        return
    apply(values)
    _loaded_at = time.monotonic()


def describe(overrides: dict[str, Any]) -> list[dict]:
    s = get_settings()
    out = []
    for f in FIELDS:
        value = getattr(s, f.key)
        default = base_value(f.key)
        if f.key == "search_vertical_sources":  # None 表示全部
            every = [n for n, _ in _engines()[1]]
            value = every if value is None else value
            default = every if default is None else default
        out.append({"key": f.key, "label": f.label, "group": f.group, "type": f.type, "value": value,
                    "default": default, "options": options_for(f), "min": f.min, "max": f.max, "help": f.help,
                    "overridden": f.key in overrides})
    return out
