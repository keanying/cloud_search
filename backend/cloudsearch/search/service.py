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
from ..contracts import SearchHit
from .engines import ENGINES, EngineBlocked, looks_relevant

log = logging.getLogger(__name__)


class EngineHealth:
    """进程内引擎健康状态：被拦截后冷却一段时间。"""

    def __init__(self) -> None:
        self._blocked_until: dict[str, float] = {}

    def available(self, names: list[str]) -> list[str]:
        now = time.monotonic()
        return [n for n in names if n in ENGINES and self._blocked_until.get(n, 0) <= now]

    def block(self, name: str) -> None:
        self._blocked_until[name] = time.monotonic() + get_settings().search_engine_cooldown_s

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
    blocked_engines: list[str] = field(default_factory=list)


async def browser_search(s: CloudBrowserSession, queries: list[str], *, per_query: int | None = None,
                         exclude_domains: list[str] | None = None,
                         before_each: Callable[[], Awaitable[None]] | None = None) -> SearchReport:
    settings = get_settings()
    per_query = per_query or settings.search_results_per_query
    exclude = [d.lower().lstrip(".") for d in (exclude_domains or [])]
    report = SearchReport()
    seen: set[str] = set()
    for qi, query in enumerate(queries):
        if before_each:
            await before_each()  # 栅栏检查：停止后不再发起新搜索
        engines = health.available(settings.search_engines)
        if not engines:
            report.per_query[query] = "所有搜索引擎暂时不可用（被拦截冷却中）"
            continue
        # 轮换起点，分散负载
        engines = engines[qi % len(engines):] + engines[: qi % len(engines)]
        got: list[SearchHit] = []
        for name in engines:
            try:
                async with s.lock:
                    got = await ENGINES[name].search(s, query, per_query)
            except EngineBlocked:
                health.block(name)
                report.blocked_engines.append(name)
                log.warning("search engine %s blocked; cooling down", name)
                continue
            except Exception as e:  # noqa: BLE001
                log.warning("search engine %s failed: %s", name, e)
                continue
            if got and not looks_relevant(query, got):
                log.warning("search engine %s returned irrelevant results for %r; trying next", name, query)
                got = []
                continue
            if got:
                report.per_query[query] = name
                break
        if not got:
            report.per_query.setdefault(query, "无结果")
        for h in got:
            host = (urlsplit(h.url).hostname or "").lower()
            if any(host == d or host.endswith("." + d) for d in exclude):
                continue
            key = normalize_url(h.url)
            if key in seen:
                continue
            seen.add(key)
            report.hits.append(h)
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
