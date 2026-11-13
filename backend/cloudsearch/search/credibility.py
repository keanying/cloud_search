"""来源可信度分级（启发式，按域名）：用于挑选要读的网页、冲突取舍提示和界面展示。

等级（分数越高越优先）：
  official 官方（政府、机构/企业官网、交易所、标准组织）    5
  academic 学术（高校、科研机构、期刊、论文库）              4
  media    权威媒体（主流新闻机构）                          4
  reference 百科（维基百科、百度百科等）                    3
  community 社区/自媒体（问答、博客、公众号、论坛）         2
  aggregate 聚合/转载（文库、聚合站、内容农场）             1
  unknown   未识别                                          2
分级只是排序和提示，不是对内容真伪的判断；证据仍须逐字核对。
"""

from __future__ import annotations

from urllib.parse import urlsplit

LABELS = {"official": "官方", "academic": "学术", "media": "权威媒体", "reference": "百科",
          "community": "社区/自媒体", "aggregate": "聚合/转载", "unknown": "一般网站"}
SCORES = {"official": 5, "academic": 4, "media": 4, "reference": 3, "community": 2, "aggregate": 1, "unknown": 2}

_SUFFIX = [
    (("gov.cn", ".gov", ".gov.uk", ".gov.hk", ".gov.tw", ".mil", "europa.eu", "un.org", "who.int", "worldbank.org",
      "imf.org", "oecd.org", "iso.org", "w3.org", "ietf.org", "sse.com.cn", "szse.cn", "hkex.com.hk", "sec.gov",
      "csrc.gov.cn", "pbc.gov.cn", "stats.gov.cn"), "official"),
    ((".edu", ".edu.cn", ".ac.cn", ".ac.uk", "arxiv.org", "nature.com", "science.org", "sciencedirect.com",
      "springer.com", "ieee.org", "acm.org", "cnki.net", "nih.gov", "pubmed.ncbi.nlm.nih.gov", "researchgate.net",
      "semanticscholar.org", "openreview.net"), "academic"),
    (("xinhuanet.com", "news.cn", "people.com.cn", "cctv.com", "chinanews.com.cn", "chinadaily.com.cn",
      "thepaper.cn", "caixin.com", "yicai.com", "21jingji.com", "jiemian.com", "36kr.com", "huxiu.com",
      "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com", "ft.com", "wsj.com", "bloomberg.com",
      "economist.com", "theguardian.com", "cnbc.com", "techcrunch.com", "theverge.com", "wired.com",
      "nikkei.com", "scmp.com", "cls.cn", "stcn.com", "cs.com.cn", "eastmoney.com"), "media"),
    (("wikipedia.org", "baike.baidu.com", "baike.sogou.com", "britannica.com", "zh.wikipedia.org"), "reference"),
    (("zhihu.com", "weixin.qq.com", "mp.weixin.qq.com", "weibo.com", "douban.com", "csdn.net", "jianshu.com",
      "medium.com", "reddit.com", "stackoverflow.com", "github.com", "bilibili.com", "xiaohongshu.com",
      "tieba.baidu.com", "juejin.cn", "segmentfault.com", "substack.com", "quora.com", "toutiao.com"),
     "community"),
    (("wenku.baidu.com", "baijiahao.baidu.com", "sohu.com", "163.com", "doc88.com", "docin.com",
      "book118.com", "360doc.com", "sina.com.cn", "qq.com", "ifeng.com", "jingyan.baidu.com", "zhidao.baidu.com"),
     "aggregate"),
]


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def classify(url: str, *, preferred: list[str] | None = None) -> str:
    """返回等级键。preferred：本任务规划阶段认定的权威站点（如某机构官网）视为 official。"""
    host = _host(url)
    if not host:
        return "unknown"
    for d in preferred or []:
        d = d.lower().lstrip(".").removeprefix("www.")
        if d and (host == d or host.endswith("." + d)):
            return "official"
    for suffixes, label in _SUFFIX:
        for suf in suffixes:
            s = suf.lstrip(".")
            if host == s or host.endswith("." + s) or (suf.startswith(".") and host.endswith(suf)):
                return label
    return "unknown"


def score(url: str, *, preferred: list[str] | None = None) -> int:
    return SCORES[classify(url, preferred=preferred)]


def label(url: str, *, preferred: list[str] | None = None) -> str:
    return LABELS[classify(url, preferred=preferred)]
