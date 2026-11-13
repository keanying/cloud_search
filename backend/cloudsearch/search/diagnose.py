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


async def _diagnose(query: str) -> int:
    s = get_settings()
    await auto_migrate()
    from ..browser.launch import resolve

    choice = resolve()
    print(f"浏览器：{choice['detail']}")
    print(f"代理：{s.browser_proxy or '未设置（直连）'}")
    print(f"通用引擎顺序：{', '.join(s.search_engines)}")
    print(f"测试查询：{query}\n")
    pool = get_pool()
    browser = await pool._ensure()
    ctx = await browser.new_context(locale=s.browser_locale, viewport={"width": 1280, "height": 860})
    page = await ctx.new_page()
    sess = CloudBrowserSession("diagnose", ctx, page)
    names = list(dict.fromkeys(s.search_engines + list(vertical_sources())))
    ok = 0
    try:
        for name in names:
            engine = all_engines().get(name)
            if engine is None:
                print(f"  {name:14} 未知引擎（检查 config.yaml 的 search.engines 拼写）")
                continue
            t0 = time.monotonic()
            try:
                hits = await asyncio.wait_for(engine.search(sess, query, 5), 60)
                dt = time.monotonic() - t0
                if not hits:
                    print(f"  {name:14} 无结果（{dt:.1f}s）  当前页面：{page.url[:70]}")
                elif not looks_relevant(query, hits) and name in s.search_engines:
                    print(f"  {name:14} 结果与查询无关（可能被风控返回了无关内容，{dt:.1f}s）")
                else:
                    ok += 1
                    print(f"  {name:14} 可用：{len(hits)} 条（{dt:.1f}s）  例：{(hits[0].title or '')[:30]}")
            except EngineBlocked:
                print(f"  {name:14} 需要人机验证（任务中会弹出“需要你协助”，由你在实时画面中完成）")
            except Exception as e:  # noqa: BLE001
                kind = ("无法访问（网络不通或被拒绝，可能需要在 config.yaml 设置 browser.proxy）"
                        if isinstance(e, EngineUnavailable) or is_network_error(e) else "出错")
                print(f"  {name:14} {kind}：{str(e).splitlines()[0][:90]}")
    finally:
        await ctx.close()
        await pool.close()
    print(f"\n可用 {ok}/{len(names)}。任务中会按顺序使用可用的引擎，不可用的会自动跳过。")
    return 0 if ok else 1


def main() -> None:
    query = " ".join(sys.argv[1:]) or "故宫博物院 开放时间"
    from ..serve import run_coro

    sys.exit(run_coro(_diagnose(query)))


if __name__ == "__main__":
    main()
