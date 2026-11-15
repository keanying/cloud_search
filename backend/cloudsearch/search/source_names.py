"""来源标题与站点名整理：去掉标题末尾的站点后缀（如“…_腾讯新闻”“… - 新浪财经”），
丢弃不像站点名的元数据（版权声明、备案号、过长文字），取不到时用域名。前端 lib/sourceNames.ts 保持同样规则。"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_BAD_SITE = re.compile(r"copyright|©|all rights reserved|版权所有|icp|备案|powered by|\d{4}\s*[-–]\s*\d{4}", re.I)
_SEP = re.compile(r"\s*(?:_|\||｜|——|—)\s*|\s+[-–]\s+")
MAX_SITE = 20


def host_of(url: str | None) -> str:
    h = (urlsplit(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def valid_site(name: str | None) -> str | None:
    n = " ".join((name or "").split())
    if not n or len(n) > MAX_SITE or _BAD_SITE.search(n) or "://" in n:
        return None
    return n


def _domain_like(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", name.lower()))


def tidy(title: str | None, site_name: str | None, url: str | None) -> tuple[str | None, str]:
    """返回 (整理后的标题, 站点名)。"""
    site = valid_site(site_name)
    t = " ".join((title or "").split())
    for _ in range(2):  # 最多去两层后缀，如“标题_频道_网站”
        parts = _SEP.split(t)
        if len(parts) < 2:
            break
        tail = parts[-1].strip()
        head = t[: len(t) - len(tail)].rstrip(" _|｜-–—")
        if not tail or not head or len(head) < 6:
            break
        same = bool(site) and (tail.lower() == site.lower() or site in tail or tail in site)
        if not same:
            # 尾部不是已知站点名：只有短、像站点名时才去掉
            if len(tail) > 12 or not re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9. ]{2,12}", tail):
                break
            if site and not _domain_like(site) and not _domain_like(tail):
                # 已有可读站点名，尾部是另一个名字（如频道）：去掉但保留原站点名
                t = head
                continue
            site = tail if (not site or _domain_like(site)) else site
        t = head
    return (t or None), (site or host_of(url) or "未知来源")
