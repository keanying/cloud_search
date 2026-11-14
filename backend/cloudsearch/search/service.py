"""浏览器搜索服务：多引擎轮换、拦截冷却、礼貌间隔、结果去重。"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from ..browser.pool import CloudBrowserSession
from ..core.config import get_settings
from ..contracts import SearchHit, SearchQuery
from .engines import ENGINES, EngineBlocked, EngineUnavailable, SearchEngine, is_network_error, looks_relevant
from .sources import build_sources

_registry_cache: tuple[int, dict[str, SearchEngine]] | None = None


def all_engines() -> dict[str, SearchEngine]:
    """内置引擎（duckduckgo/bing/baidu/sogou）+ 模板来源（google、垂直来源、用户自定义来源）。"""
    global _registry_cache
    custom = get_settings().search_custom_sources
    key = hash(repr(custom))
    if _registry_cache is None or _registry_cache[0] != key:
        merged: dict[str, SearchEngine] = dict(build_sources(custom))
        merged.update(ENGINES)
        _registry_cache = (key, merged)
    return {**_registry_cache[1], **ENGINES}  # 测试中替换 ENGINES 时也生效


def vertical_sources() -> dict[str, SearchEngine]:
    """可供规划选用的垂直来源。"""
    allowed = get_settings().search_vertical_sources
    out = {}
    for name, e in all_engines().items():
        cfg = getattr(e, "cfg", None)
        if cfg is None or cfg.kind != "vertical":
            continue
        if allowed is None or name in allowed:
            out[name] = e
    return out


def describe_sources() -> str:
    """给搜索规划智能体看的来源说明。"""
    s = get_settings()
    lines = [f"通用搜索引擎（按优先级，source 留空时使用）：{', '.join(s.search_engines)}"]
    for name, e in vertical_sources().items():
        lines.append(f"- {name}：{e.cfg.label}。{e.cfg.description}")
    return "\n".join(lines)

log = logging.getLogger(__name__)


class EngineHealth:
    """进程内引擎健康状态：被拦截后冷却一段时间。"""

    def __init__(self) -> None:
        self._blocked_until: dict[str, float] = {}

    def available(self, names: list[str]) -> list[str]:
        now = time.monotonic()
        reg = all_engines()
        return [n for n in names if n in reg and self._blocked_until.get(n, 0) <= now]

    def block(self, name: str, seconds: float | None = None) -> None:
        self._blocked_until[name] = time.monotonic() + (seconds or get_settings().search_engine_cooldown_s)

    def reset(self) -> None:
        self._blocked_until.clear()


health = EngineHealth()


def normalize_url(url: str) -> str:
    p = urlsplit(url)
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), (p.hostname or "").lower(), path, p.query, ""))


@dataclass
class SearchReport:
    hits: list[SearchHit] = field(default_factory=list)
    per_query: dict[str, str] = field(default_factory=dict)  # query -> engine 或失败原因
    hit_counts: dict[str, int] = field(default_factory=dict)  # query -> 去重后新增的结果数
    blocked_engines: list[str] = field(default_factory=list)
    unreachable_engines: list[str] = field(default_factory=list)


async def browser_search(s: CloudBrowserSession, queries: list[str | SearchQuery], *, per_query: int | None = None,
                         exclude_domains: list[str] | None = None,
                         before_each: Callable[[], Awaitable[None]] | None = None,
                         on_blocked: Callable[[CloudBrowserSession, str], Awaitable[bool]] | None = None
                         ) -> SearchReport:
    """按配置的引擎顺序搜索。strategy=priority：总是先用第一个可用引擎，失败/被拦截/结果无关才换下一个；
    strategy=rotate：每个查询轮换起始引擎以分散负载。"""
    from ..core.tracelog import trace

    settings = get_settings()
    per_query = per_query or settings.search_results_per_query
    exclude = [d.lower().lstrip(".") for d in (exclude_domains or [])]
    report = SearchReport()
    seen: set[str] = set()
    handed_over: set[str] = set()  # 每个引擎最多请求一次人工接管
    for qi, raw in enumerate(queries):
        sq = raw if isinstance(raw, SearchQuery) else SearchQuery(query=raw)
        if before_each:
            await before_each()  # 栅栏检查：停止后不再发起新搜索
        engines = health.available(settings.search_engines)
        # 指定了垂直来源：优先用该来源，无结果/被拦截时回退到通用引擎
        if sq.source and sq.source in vertical_sources() and health.available([sq.source]):
            engines = [sq.source] + [e for e in engines if e != sq.source]
        trace("search", f"查询「{sq.query}」", engines=engines, language=sq.language, recency=sq.recency,
              source=sq.source, purpose=sq.purpose)
        if not engines:
            trace("search", "所有搜索引擎都在冷却中（之前被拦截或网络不通），跳过", query=sq.query)
            report.per_query[sq.query] = "所有搜索引擎暂时不可用（被拦截或网络不可达，冷却中）"
            report.hit_counts[sq.query] = 0
            continue
        if settings.search_strategy == "rotate" and not sq.source:
            engines = engines[qi % len(engines):] + engines[: qi % len(engines)]
        got: list[SearchHit] = []
        for name in engines:
            engine = all_engines()[name]
            t0 = time.monotonic()
            try:
                s.challenge_reason = None
                async with s.lock:
                    got = await engine.search(s, sq.query, per_query, lang=sq.language, recency=sq.recency)
            except EngineBlocked:
                why = getattr(s, "challenge_reason", None) or "引擎判定页面为验证/拦截"
                trace("search", f"{name}：需要人机验证（{time.monotonic() - t0:.1f}s）", reason=why,
                      url=getattr(getattr(s, "page", None), "url", None))
                # 人机验证：请用户在实时画面中处理；处理完成后在同一引擎重试一次
                resolved = False
                if on_blocked is not None and name not in handed_over:
                    handed_over.add(name)
                    label = getattr(getattr(engine, "cfg", None), "label", None) or name
                    resolved = await on_blocked(s, f"{label} 要求人机验证，请完成验证后点“完成”（判定依据：{why}）")
                if resolved:
                    try:
                        async with s.lock:
                            got = await engine.search(s, sq.query, per_query, lang=sq.language, recency=sq.recency)
                    except Exception as e:  # noqa: BLE001
                        log.warning("search engine %s still unavailable after takeover: %s", name, e)
                        got = []
                if not got:
                    health.block(name)
                    report.blocked_engines.append(name)
                    log.warning("search engine %s blocked (%s); cooling down", name, why)
                    trace("search", f"{name}：未通过验证，冷却 {settings.search_engine_cooldown_s}s，换下一个引擎")
                    continue
            except Exception as e:  # noqa: BLE001
                if isinstance(e, EngineUnavailable) or is_network_error(e):
                    health.block(name, settings.search_unreachable_cooldown_s)
                    report.unreachable_engines.append(name)
                    log.warning("search engine %s unreachable (%s); cooling down", name, str(e)[:120])
                    trace("search", f"{name}：无法访问，冷却 {settings.search_unreachable_cooldown_s}s",
                          error=f"{type(e).__name__}: {str(e)[:300]}")
                else:
                    log.warning("search engine %s failed: %s", name, e)
                    trace("search", f"{name}：出错", error=f"{type(e).__name__}: {str(e)[:300]}")
                continue
            if got and not looks_relevant(sq.query, got):
                log.warning("search engine %s returned irrelevant results for %r; trying next", name, sq.query)
                trace("search", f"{name}：结果与查询无关（可能被风控返回了无关内容），换下一个引擎",
                      sample=[h.title for h in got[:3]])
                got = []
                continue
            trace("search", f"{name}：{len(got)} 条结果（{time.monotonic() - t0:.1f}s）",
                  top=[f"{h.title} | {h.url}" for h in got[:5]])
            if got:
                report.per_query[sq.query] = name
                break
        if not got:
            report.per_query.setdefault(sq.query, "无结果")
        added = 0
        for h in got:
            host = (urlsplit(h.url).hostname or "").lower()
            if any(host == d or host.endswith("." + d) for d in exclude):
                continue
            key = normalize_url(h.url)
            if key in seen:
                continue
            seen.add(key)
            report.hits.append(h)
            added += 1
        report.hit_counts[sq.query] = added
        await asyncio.sleep(random.uniform(1.0, 2.5))  # 礼貌间隔
    return report


def rank_hits(hits: list[SearchHit], limit: int) -> list[SearchHit]:
    """按各查询内名次交错选取，兼顾不同查询的覆盖；同域名最多 3 条。"""
    by_query: dict[str, list[SearchHit]] = {}
    for h in hits:
        by_query.setdefault(h.query, []).append(h)
    for v in by_query.values():
        v.sort(key=lambda h: h.rank)
    picked: list[SearchHit] = []
    per_host: dict[str, int] = {}
    depth = 0
    while len(picked) < limit and any(len(v) > depth for v in by_query.values()):
        for v in by_query.values():
            if depth < len(v) and len(picked) < limit:
                h = v[depth]
                host = urlsplit(h.url).hostname or ""
                if per_host.get(host, 0) < 3:
                    per_host[host] = per_host.get(host, 0) + 1
                    picked.append(h)
        depth += 1
    return picked
