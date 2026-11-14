"""搜索引擎连通性诊断：python -m cloudsearch.search.diagnose [查询词]

用当前 config.yaml（含 browser.proxy、浏览器内核）逐个打开已配置的搜索引擎/来源，报告：
可用（结果数、耗时）/ 需要人机验证 / 无法访问 / 无结果。用于判断本机网络下哪些引擎可用。
"""

from __future__ import annotations

import asyncio
import sys
import time

from ..browser.pool import CloudBrowserSession, get_pool
from ..core.config import get_settings
from ..db.migrate import auto_migrate
from .engines import EngineBlocked, EngineUnavailable, is_network_error, looks_relevant
from .service import all_engines, vertical_sources


async def diagnose_engines(query: str, names: list[str] | None = None, *, per_engine_timeout: float = 60
                           ) -> list[dict]:
    """逐个打开引擎/来源搜索 query，返回每个的状态（命令行与管理后台共用）。
    status：ok 可用 / empty 无结果 / irrelevant 结果无关 / blocked 需要人机验证 / unreachable 无法访问 / error 出错"""
    from ..core.runtime import engine_label

    s = get_settings()
    if names is None:
        names = list(dict.fromkeys(s.search_engines + list(vertical_sources())))
    pool = get_pool()
    browser = await pool._ensure()
    ctx = await browser.new_context(locale=s.browser_locale, viewport={"width": 1280, "height": 860})
    page = await ctx.new_page()
    sess = CloudBrowserSession("diagnose", ctx, page)
    out: list[dict] = []
    try:
        for name in names:
            row = {"name": name, "label": engine_label(name), "status": "error", "count": 0, "seconds": 0.0,
                   "sample": None, "detail": None}
            out.append(row)
            engine = all_engines().get(name)
            if engine is None:
                row["detail"] = "未知引擎（检查 config.yaml 的 search.engines 拼写）"
                continue
            t0 = time.monotonic()
            try:
                hits = await asyncio.wait_for(engine.search(sess, query, 5), per_engine_timeout)
                row["count"] = len(hits)
                if not hits:
                    row["status"], row["detail"] = "empty", f"当前页面：{page.url[:80]}"
                elif not looks_relevant(query, hits) and name in s.search_engines:
                    row["status"], row["detail"] = "irrelevant", "可能被风控返回了无关内容"
                else:
                    row["status"], row["sample"] = "ok", (hits[0].title or "")[:60]
            except EngineBlocked:
                row["status"], row["detail"] = "blocked", "任务中会弹出“需要你协助”，由你在实时画面中完成验证"
            except Exception as e:  # noqa: BLE001
                unreachable = isinstance(e, EngineUnavailable) or is_network_error(e)
                row["status"] = "unreachable" if unreachable else "error"
                msg = (str(e).splitlines() or [type(e).__name__])[0][:120]
                row["detail"] = (msg + "（网络不通或被拒绝，可能需要在 config.yaml 设置 browser.proxy）"
                                 if unreachable else msg)
            row["seconds"] = round(time.monotonic() - t0, 1)
    finally:
        await ctx.close()
    return out


_TEXT = {"ok": "可用", "empty": "无结果", "irrelevant": "结果与查询无关", "blocked": "需要人机验证",
         "unreachable": "无法访问", "error": "出错"}


async def _diagnose(query: str) -> int:
    s = get_settings()
    await auto_migrate()
    from ..browser.launch import resolve
    from ..core import runtime

    await runtime.refresh(force=True)
    choice = resolve()
    print(f"浏览器：{choice['detail']}")
    print(f"代理：{s.browser_proxy or '未设置（直连）'}")
    print(f"通用引擎顺序：{', '.join(s.search_engines)}")
    print(f"测试查询：{query}\n")
    try:
        rows = await diagnose_engines(query)
    finally:
        await get_pool().close()
    for r in rows:
        extra = f"：{r['count']} 条  例：{r['sample']}" if r["status"] == "ok" else (
            f"：{r['detail']}" if r["detail"] else "")
        print(f"  {r['name']:14} {_TEXT[r['status']]}（{r['seconds']}s）{extra}")
    ok = sum(1 for r in rows if r["status"] == "ok")
    print(f"\n可用 {ok}/{len(rows)}。任务中会按顺序使用可用的引擎，不可用的会自动跳过。")
    return 0 if ok else 1


def main() -> None:
    query = " ".join(sys.argv[1:]) or "故宫博物院 开放时间"
    from ..serve import run_coro

    sys.exit(run_coro(_diagnose(query)))


if __name__ == "__main__":
    main()
