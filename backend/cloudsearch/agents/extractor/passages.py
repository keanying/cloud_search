"""长网页段落挑选：不是简单截断前 N 字，而是按与问题/字段/核心对象的相关度挑段落。

- 按段落（空行/换行）切分，再合并成约 chunk 字的块；
- 用中文二字组 + 英文词与关键词集合的重合度打分；开头一块总是保留（标题、导语、发布信息常在这里）；
- 在预算内选分数最高的块，按原文顺序拼接，跳过处用「……（略去 N 字）……」标注。
摘录的逐字校验始终针对完整正文进行，因此不影响证据核对。
"""

from __future__ import annotations

import re

_SPLIT = re.compile(r"\n\s*\n|\n")


def _grams(text: str) -> set[str]:
    text = text.lower()
    out = set(re.findall(r"[a-z0-9][a-z0-9.\-]{1,}", text))
    for seg in re.findall(r"[一-鿿]+", text):
        out.update(seg[i:i + 2] for i in range(len(seg) - 1))
    return out


def chunk_text(text: str, chunk: int = 1200) -> list[tuple[int, str]]:
    """返回 [(起始位置, 块文本)]，块边界尽量落在段落处。"""
    blocks: list[tuple[int, str]] = []
    pos = 0
    buf, start = "", 0
    for part in _SPLIT.split(text):
        idx = text.find(part, pos)
        if idx < 0:
            idx = pos
        pos = idx + len(part)
        if not part.strip():
            continue
        if not buf:
            start = idx
        if len(buf) + len(part) > chunk and buf:
            blocks.append((start, buf))
            buf, start = part, idx
        else:
            buf = (buf + "\n" + part) if buf else part
        while len(buf) > chunk * 2:  # 超长段落硬切
            blocks.append((start, buf[:chunk]))
            start += chunk
            buf = buf[chunk:]
    if buf:
        blocks.append((start, buf))
    return blocks


def select_passages(text: str, terms: list[str], budget: int = 12000, chunk: int = 1200) -> str:
    if len(text) <= budget:
        return text
    blocks = chunk_text(text, chunk)
    if not blocks:
        return text[:budget]
    want = set().union(*(_grams(t) for t in terms if t)) if terms else set()
    scored = []
    for i, (_, b) in enumerate(blocks):
        g = _grams(b)
        overlap = len(want & g) / (len(want) or 1)
        digits = min(len(re.findall(r"\d", b)) / 40, 0.3)  # 含数字的段落对事实/字段更有价值
        scored.append((overlap + digits + (1.0 if i == 0 else 0.0), i))
    chosen: set[int] = set()
    used = 0
    for _, i in sorted(scored, reverse=True):
        size = len(blocks[i][1])
        if used + size > budget and chosen:
            continue
        chosen.add(i)
        used += size
        if used >= budget:
            break
    out: list[str] = []
    last_end = 0
    for i in sorted(chosen):
        start, b = blocks[i]
        if start > last_end + 1:
            out.append(f"……（略去约 {start - last_end} 字）……")
        out.append(b)
        last_end = start + len(b)
    if last_end < len(text) - 1:
        out.append(f"……（略去约 {len(text) - last_end} 字）……")
    return "\n".join(out)
