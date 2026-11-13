"""可配置的搜索来源：通用搜索引擎之外，还可以直接用各网站自己的站内搜索（垂直来源）。

每个来源 = 搜索地址模板 + 结果选择器。内置：Google、中英文维基百科、百度百科、微信公众号文章（搜狗微信）、
GitHub、arXiv。近期新闻请用通用引擎 + recency 时间过滤。用户可在 config.yaml 的 search.custom_sources 中添加任意网站。
搜索规划智能体会根据意图为每条查询选择合适的来源（SearchQuery.source）；来源无结果时回退到通用引擎。
"""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import quote_plus, urljoin

from pydantic import BaseModel, Field

from ..browser.pool import CloudBrowserSession
from ..contracts import SearchHit
from .engines import GENERIC_JS, EngineBlocked, SearchEngine, query_language


class SourceConfig(BaseModel, extra="forbid"):
    name: str = Field(description="英文标识，如 wikipedia_zh")
    label: str = Field(description="中文名称，如 中文维基百科")
    description: str = Field(default="", description="适用场景（会告诉搜索规划智能体）")
    kind: Literal["general", "vertical"] = "vertical"
    url: str = Field(description="搜索地址模板：{q} 为编码后的查询词，{hl} 为 zh-CN/en")
    item: str = Field(description="每条结果的容器选择器")
    link: str = Field(default="a[href]", description="容器内链接选择器")
    title: str | None = Field(default=None, description="容器内标题选择器（默认用链接文字）")
    snippet: str | None = Field(default=None, description="容器内摘要选择器")
    wait: str | None = Field(default=None, description="等待出现的选择器（默认等 item）")
    direct_hit: str | None = Field(default=None, description="最终网址匹配该正则时，说明直接进入了词条页，整页即结果")
    block_patterns: str = Field(default=r"captcha|/sorry/|antispider|unusual traffic|人机验证|安全验证|验证码",
                                description="出现在网址或页面文字中即视为被拦截")


BUILTIN_SOURCES: list[SourceConfig] = [
    SourceConfig(name="google", label="Google", kind="general", description="通用网页搜索（境外资料更全）",
                 url="https://www.google.com/search?q={q}&hl={hl}&num=10",
                 item="#search div.MjjYud, #search div.g", link="a[href^='http']", title="h3",
                 snippet="div.VwiC3b, div[data-sncf], span.aCOpRe", wait="#search"),
    SourceConfig(name="wikipedia_zh", label="中文维基百科", description="百科概念、人物、地理、历史等背景知识（中文）",
                 url="https://zh.wikipedia.org/w/index.php?search={q}&fulltext=1&ns0=1",
                 item="li.mw-search-result", link=".mw-search-result-heading a", snippet=".searchresult",
                 direct_hit=r"zh\.wikipedia\.org/wiki/(?!Special:)"),
    SourceConfig(name="wikipedia_en", label="English Wikipedia", description="百科背景知识（英文，国际话题更全）",
                 url="https://en.wikipedia.org/w/index.php?search={q}&fulltext=1&ns0=1",
                 item="li.mw-search-result", link=".mw-search-result-heading a", snippet=".searchresult",
                 direct_hit=r"en\.wikipedia\.org/wiki/(?!Special:)"),
    SourceConfig(name="baike", label="百度百科", description="中文百科词条：机构、景点、人物、术语的基本信息",
                 url="https://baike.baidu.com/search?word={q}&pn=0&rn=10&enc=utf8",
                 # 新版页面类名带随机后缀（如 title_zEzpF），按前缀匹配；fengchao 为推广，排除
                 item="[class*='listWrap_'] > [class*='container_']:not([class*='fengchao'])",
                 link="a[class*='title_']", snippet="[class*='abstract'], [class*='summary'], [class*='desc']",
                 direct_hit=r"baike\.baidu\.com/item/"),
    SourceConfig(name="weixin", label="微信公众号文章", description="中文公众号文章：机构公告转发、行业解读、活动信息",
                 url="https://weixin.sogou.com/weixin?type=2&query={q}", item="ul.news-list > li",
                 link="h3 a", snippet="p.txt-info"),
    SourceConfig(name="github", label="GitHub", description="开源项目、代码、技术工具",
                 url="https://github.com/search?q={q}&type=repositories",
                 item="div[data-testid='results-list'] > div", link="h3 a, a[href^='/'][data-testid]",
                 snippet="span.search-match, p", wait="div[data-testid='results-list']"),
    SourceConfig(name="arxiv", label="arXiv 论文", description="学术论文预印本（英文）：计算机、物理、数学等",
                 url="https://arxiv.org/search/?query={q}&searchtype=all", item="li.arxiv-result",
                 link="p.list-title a", title="p.title", snippet="span.abstract-short"),
]

_JS = r"""(cfg) => {
  const out = [];
  for (const it of document.querySelectorAll(cfg.item)) {
    const a = it.querySelector(cfg.link);
    if (!a) continue;
    const t = cfg.title ? it.querySelector(cfg.title) : null;
    const sn = cfg.snippet ? it.querySelector(cfg.snippet) : null;
    out.push({url: a.getAttribute('href'), title: (t || a).textContent, snippet: sn ? sn.textContent : null});
  }
  return out;
}"""


class TemplateSource(SearchEngine):
    def __init__(self, cfg: SourceConfig):
        self.cfg = cfg
        self.name = cfg.name
        self.host = re.sub(r"^https?://([^/]+)/.*$", r"\1", cfg.url).removeprefix("www.")

    async def search(self, s: CloudBrowserSession, query: str, n: int, *, lang: str | None = None,
                     recency: str | None = None) -> list[SearchHit]:
        hl = "zh-CN" if query_language(query, lang) == "zh" else "en"
        url = self.cfg.url.replace("{q}", quote_plus(query)).replace("{hl}", hl)
        await s.goto(url, activity=f"{self.cfg.label} 搜索：{query}", check=False)
        try:
            await s.page.wait_for_selector(self.cfg.wait or self.cfg.item, state="attached", timeout=10000)
        except Exception:  # noqa: BLE001
            pass
        await s.capture_frame(force=True)
        page_url = s.page.url
        text = await s.page.evaluate("() => (document.body ? document.body.innerText : '').slice(0, 800)")
        if re.search(self.cfg.block_patterns, page_url, re.I) or (
                len(text) < 800 and re.search(self.cfg.block_patterns, text, re.I)):
            raise EngineBlocked(self.name)
        if self.cfg.direct_hit and re.search(self.cfg.direct_hit, page_url):
            title = await s.page.title()
            return [SearchHit(engine=self.name, query=query, rank=1, url=page_url, title=title, snippet=None)]
        rows = await s.page.evaluate(_JS, self.cfg.model_dump())
        base = page_url if page_url.startswith(("http://", "https://")) else self.cfg.url.replace("{q}", "")
        for r in rows:
            if r.get("url"):
                r["url"] = urljoin(base, r["url"])
        if not rows and self.cfg.kind == "general":
            rows = await s.page.evaluate(GENERIC_JS, self.host)
        return self._hits(query, rows, n)


def build_sources(custom: list[dict] | None = None) -> dict[str, TemplateSource]:
    out = {c.name: TemplateSource(c) for c in BUILTIN_SOURCES}
    for raw in custom or []:
        cfg = SourceConfig.model_validate(raw)
        out[cfg.name] = TemplateSource(cfg)
    return out
