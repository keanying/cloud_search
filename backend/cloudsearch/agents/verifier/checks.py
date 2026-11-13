"""确定性核验：原文摘录逐字定位（忽略空白差异）。"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")


def _squash(s: str) -> tuple[str, list[int]]:
    """去除空白，并记录压缩后每个字符在原文中的位置。"""
    out, pos = [], []
    for i, ch in enumerate(s):
        if not ch.isspace():
            out.append(ch)
            pos.append(i)
    return "".join(out), pos


def locate_quote(text: str, quote: str) -> tuple[int, int] | None:
    """返回摘录在原文中的 [start, end)；找不到返回 None。"""
    quote = quote.strip().strip("“”\"'…").strip()
    if len(quote) < 4:
        return None
    i = text.find(quote)
    if i >= 0:
        return i, i + len(quote)
    sq_text, pos = _squash(text)
    sq_quote, _ = _squash(quote)
    j = sq_text.find(sq_quote)
    if j < 0 or not sq_quote:
        return None
    return pos[j], pos[j + len(sq_quote) - 1] + 1
