"""报告配图（SVG，自包含、不依赖脚本）：阶段总览图、分层结构图、封面横幅。

同一份 SVG 用于对话中的展示、HTML/PDF 导出，Word 导出时由浏览器转成 PNG。
内容来自撰写智能体给出的结构化数据（阶段、里程碑、层级与节点），不是生成式插画。
"""

from __future__ import annotations

import hashlib
import html as _html
import math
from typing import Any

FONT = "'PingFang SC','Microsoft YaHei','Noto Sans CJK SC','Source Han Sans SC','WenQuanYi Zen Hei',sans-serif"
STAGE_COLORS = ["#3b6fb6", "#16879a", "#2f8a5f", "#b07419", "#7a52aa", "#c2416b", "#4b5563"]


def _esc(s: Any) -> str:
    return _html.escape(str(s or ""), quote=True)


def _w(s: str, size: float) -> float:
    """估算文字宽度：中日韩与全角字符按 1em，其余按 0.56em。"""
    return sum(size if ord(ch) > 0x2E80 else size * 0.56 for ch in s)


def wrap(text: str, size: float, max_w: float, max_lines: int = 3) -> list[str]:
    """按估算宽度折行（中英文混排逐字切分，英文尽量在空格处断开）。"""
    text = " ".join(str(text or "").split())
    lines, cur = [], ""
    for ch in text:
        if _w(cur + ch, size) <= max_w:
            cur += ch
            continue
        cut = cur.rfind(" ")
        if ch != " " and cut > len(cur) * 0.3:
            lines.append(cur[:cut])
            cur = cur[cut + 1:] + ch
        else:
            lines.append(cur)
            cur = ch.lstrip()
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    elif len(lines) == max_lines and cur:
        lines[-1] = lines[-1][:-1] + "…"
    return lines or [""]


def _tint(hex_color: str, amount: float) -> str:
    """与白色混合：amount=0.9 表示 90% 白。"""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    mix = lambda c: round(c + (255 - c) * amount)  # noqa: E731
    return f"#{mix(r):02x}{mix(g):02x}{mix(b):02x}"


def _text(x: float, y: float, s: str, size: float, fill: str, weight: int = 400, anchor: str = "start") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}">{_esc(s)}</text>')


# ---------------------------------------------------------------- 阶段总览
def stages_svg(spec: dict) -> str:
    """阶段总览：左侧年代 + 序号圆点 + 右侧卡片（阶段名、里程碑、主线），各阶段不同颜色。"""
    stages = spec.get("stages") or []
    W, card_x = 1200, 330
    card_w = W - card_x - 50
    parts: list[str] = []
    y = 70
    parts.append(_text(50, y, spec.get("title") or "发展阶段总览", 34, "#0f2747", 700))
    if spec.get("subtitle"):
        y += 42
        parts.append(_text(50, y, spec["subtitle"], 19, "#64748b"))
    # 图例
    y += 40
    lx = 50.0
    for i, st in enumerate(stages):
        c = STAGE_COLORS[i % len(STAGE_COLORS)]
        name = (st.get("short") or st.get("title") or "")[:10]
        parts.append(f'<circle cx="{lx + 5:.1f}" cy="{y - 5}" r="5" fill="{c}"/>')
        parts.append(_text(lx + 16, y, name, 14, "#475569"))
        lx += 16 + _w(name, 14) + 26
    y += 26
    parts.append(f'<line x1="50" y1="{y}" x2="{W - 50}" y2="{y}" stroke="#e2e8f0" stroke-width="1.5"/>')
    y += 30
    centers = []
    for i, st in enumerate(stages):
        c = STAGE_COLORS[i % len(STAGE_COLORS)]
        title_lines = wrap(st.get("title") or "", 26, card_w - 60, 2)
        ms = "｜".join(m for m in (st.get("milestones") or []) if m)
        ms_lines = wrap(ms, 18, card_w - 60, 3) if ms else []
        main_lines = wrap(f"主线：{st['mainline']}" if st.get("mainline") else "", 16, card_w - 60, 3) \
            if st.get("mainline") else []
        h = 30 + len(title_lines) * 34 + (10 + len(ms_lines) * 26 if ms_lines else 0) \
            + (12 + len(main_lines) * 24 if main_lines else 0) + 24
        parts.append(f'<rect x="{card_x}" y="{y}" width="{card_w}" height="{h}" rx="16" fill="{_tint(c, 0.9)}"/>')
        parts.append(f'<rect x="{card_x}" y="{y}" width="6" height="{h}" fill="{c}"/>')
        ty = y + 30
        for ln in title_lines:
            ty += 26
            parts.append(_text(card_x + 30, ty, ln, 26, "#0f172a", 700))
            ty += 8
        if ms_lines:
            ty += 10
            for ln in ms_lines:
                ty += 22
                parts.append(_text(card_x + 30, ty, ln, 18, c, 600))
                ty += 4
        if main_lines:
            ty += 12
            for ln in main_lines:
                ty += 20
                parts.append(_text(card_x + 30, ty, ln, 16, "#475569"))
                ty += 4
        # 左侧年代与序号
        py = y + 46
        for ln in wrap(st.get("period") or "", 19, card_x - 42 - 28 - 50, 3):
            parts.append(_text(50, py, ln, 19, c, 700))
            py += 26
        cy = y + 40
        centers.append((cy, c))
        parts.append(f'<circle cx="{card_x - 42}" cy="{cy}" r="19" fill="#fff" stroke="{c}" stroke-width="2.5"/>')
        parts.append(_text(card_x - 42, cy + 6, f"{i + 1:02d}", 15, c, 700, "middle"))
        y += h + 22
    for (y1, _), (y2, _c) in zip(centers, centers[1:], strict=False):
        parts.insert(0, f'<line x1="{card_x - 42}" y1="{y1 + 22}" x2="{card_x - 42}" y2="{y2 - 22}" '
                        f'stroke="#cbd5e1" stroke-width="2"/>')
    y += 4
    parts.append(f'<line x1="50" y1="{y}" x2="{W - 50}" y2="{y}" stroke="#e2e8f0" stroke-width="1.5"/>')
    for ln in ([spec["note"]] if spec.get("note") else []) + (
            [f"来源：报告参考来源第 {'、'.join(str(n) for n in spec['sources'])} 条"] if spec.get("sources") else []):
        for sub in wrap(ln, 15, W - 100, 2):
            y += 30
            parts.append(_text(50, y, sub, 15, "#64748b"))
    H = y + 36
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'font-family="{FONT}"><rect width="{W}" height="{H}" fill="#fbfbf8"/>{"".join(parts)}</svg>')


# ---------------------------------------------------------------- 分层结构图
LAYER_FILLS = [("#eff6ff", "#a7c4e4"), ("#f0fbf7", "#86d1b8"), ("#fffbeb", "#e8d48a"), ("#f8f7ff", "#c9b8e8"),
               ("#fdf2f8", "#efb3d1")]


def layers_svg(spec: dict) -> str:
    """分层结构图：顶部问题框 → 若干层（层名 + 一行节点，节点之间箭头或连线）→ 底部结论框；层间可带说明标签。"""
    layers = spec.get("layers") or []
    links = spec.get("links") or []
    W = 1000
    parts: list[str] = []
    defs = ('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
            'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#1f2937"/></marker></defs>')
    y = 24
    # 顶部问题框
    tlines = wrap(spec.get("title") or "", 24, 620, 2)
    tw = max(_w(ln, 24) for ln in tlines) + 56
    th = 22 + len(tlines) * 32
    parts.append(f'<rect x="{(W - tw) / 2:.1f}" y="{y}" width="{tw:.1f}" height="{th}" fill="#1e1b6b"/>')
    for k, ln in enumerate(tlines):
        parts.append(_text(W / 2, y + 40 + k * 32, ln, 24, "#ffffff", 600, "middle"))
    prev_bottom = y + th
    for li, layer in enumerate(layers):
        label = links[li] if li < len(links) else ""
        gap = 110 if (label and li > 0) else 64
        top = prev_bottom + gap
        mid = (prev_bottom + top) / 2
        dash = ' stroke-dasharray="3 5"' if (label and li > 0) else ""
        parts.append(f'<line x1="{W / 2}" y1="{prev_bottom}" x2="{W / 2}" y2="{top - 2}" stroke="#1f2937" '
                     f'stroke-width="2.5"{dash} marker-end="url(#arr)"/>')
        if label and li > 0:
            lw = _w(label, 20) + 24
            parts.append(f'<rect x="{(W - lw) / 2:.1f}" y="{mid - 18:.1f}" width="{lw:.1f}" height="34" fill="#f3e8ff"/>')
            parts.append(_text(W / 2, mid + 7, label, 20, "#3b2f74", 500, "middle"))
        nodes = [n for n in (layer.get("nodes") or []) if n][:4] or [""]
        n = len(nodes)
        conn = 56
        max_nw = (W - 80 - conn * (n - 1)) / n
        node_lines = [wrap(t, 20, max_nw - 28, 3) for t in nodes]
        node_ws = [min(max_nw, max(_w(ln, 20) for ln in ls) + 28) for ls in node_lines]
        node_h = max(len(ls) for ls in node_lines) * 30 + 26
        row_w = sum(node_ws) + conn * (n - 1)
        box_w = min(W - 20, row_w + 70)
        fill, stroke = LAYER_FILLS[li % len(LAYER_FILLS)]
        box_h = 54 + node_h + 30
        bx = (W - box_w) / 2
        parts.append(f'<rect x="{bx:.1f}" y="{top}" width="{box_w:.1f}" height="{box_h}" fill="{fill}" stroke="{stroke}" '
                     f'stroke-width="1.5"/>')
        parts.append(_text(W / 2, top + 34, layer.get("name") or "", 22, "#111827", 500, "middle"))
        x = (W - row_w) / 2
        ny = top + 54
        for k, (ls, nw) in enumerate(zip(node_lines, node_ws, strict=False)):
            parts.append(f'<rect x="{x:.1f}" y="{ny}" width="{nw:.1f}" height="{node_h}" fill="#fff4dc" '
                         f'stroke="#f0d9a8" stroke-width="1.2"/>')
            ty = ny + node_h / 2 - (len(ls) - 1) * 15 + 7
            for j, ln in enumerate(ls):
                parts.append(_text(x + nw / 2, ty + j * 30, ln, 20, "#1f2937", 400, "middle"))
            if k < n - 1:
                x2 = x + nw + conn
                arrow = ' marker-end="url(#arr)"' if layer.get("flow", True) else ""
                parts.append(f'<line x1="{x + nw:.1f}" y1="{ny + node_h / 2}" x2="{x2 - (3 if arrow else 0):.1f}" '
                             f'y2="{ny + node_h / 2}" stroke="#1f2937" stroke-width="2"{arrow}/>')
            x += nw + conn
        prev_bottom = top + box_h
    if spec.get("note"):
        nlines = wrap(spec["note"], 20, 760, 3)
        nw = max(_w(ln, 20) for ln in nlines) + 40
        top = prev_bottom + 64
        parts.append(f'<line x1="{W / 2}" y1="{prev_bottom}" x2="{W / 2}" y2="{top}" stroke="#1f2937" stroke-width="2.5"/>')
        nh = 26 + len(nlines) * 30
        parts.append(f'<rect x="{(W - nw) / 2:.1f}" y="{top}" width="{nw:.1f}" height="{nh}" fill="#f3f4f6" '
                     f'stroke="#d1d5db" stroke-width="1.2"/>')
        for k, ln in enumerate(nlines):
            parts.append(_text(W / 2, top + 36 + k * 30, ln, 20, "#334155", 400, "middle"))
        prev_bottom = top + nh
    H = prev_bottom + 24
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'font-family="{FONT}">{defs}<rect width="{W}" height="{H}" fill="#ffffff"/>{"".join(parts)}</svg>')


# ---------------------------------------------------------------- 封面横幅
def cover_svg(title: str, subtitle: str = "", kicker: str = "云搜浏览器 · 研究报告", *, with_text: bool = True,
              height: int = 560) -> str:
    """封面横幅：浅色幻彩渐变 + 由标题决定的抽象“知识网络”图案 + 标题文字（同一标题得到同一图案）。"""
    W, H = 1600, height
    seed = int(hashlib.sha256(title.encode("utf-8")).hexdigest()[:12], 16)

    def rnd() -> float:
        nonlocal seed
        seed = (seed * 6364136223846793005 + 1442695040888963407) % (1 << 64)
        return (seed >> 11) / float(1 << 53)

    pts = []
    for _ in range(22):
        a, r = rnd() * math.tau, 60 + rnd() * 210
        pts.append((1310 + math.cos(a) * r * 1.0, H / 2 + math.sin(a) * r * 0.95 * H / 560, 5 + rnd() * 9))
    lines = []
    for i, (x1, y1, _) in enumerate(pts):
        near = sorted(pts, key=lambda p: (p[0] - x1) ** 2 + (p[1] - y1) ** 2)[1:3]
        for x2, y2, _ in near:
            lines.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="url(#ln)" '
                         f'stroke-width="1.6" opacity="0.55"/>')
    dots = "".join(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.1f}" fill="url(#dot)" opacity="0.92"/>' for x, y, r in pts)
    title_lines = wrap(title, 60, 920, 2)
    sub_lines = wrap(subtitle, 24, 920, 2) if subtitle else []
    ty = 230 if len(title_lines) == 1 else 190
    texts = [_text(96, ty - 88, kicker, 22, "#5b5cf6", 700)]
    for k, ln in enumerate(title_lines):
        texts.append(_text(96, ty + k * 76, ln, 60, "#141a3a", 800))
    sy = ty + (len(title_lines) - 1) * 76 + 64
    for k, ln in enumerate(sub_lines):
        texts.append(_text(98, sy + k * 36, ln, 24, "#475569", 400))
    grid = "".join(f'<line x1="{x}" y1="0" x2="{x}" y2="{H}" stroke="#ffffff" stroke-opacity="0.45"/>'
                   for x in range(0, W, 48))
    grid += "".join(f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="#ffffff" stroke-opacity="0.45"/>'
                    for y in range(0, H, 48))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}">'
            '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#fde7f6"/><stop offset=".35" stop-color="#e7e2ff"/>'
            '<stop offset=".7" stop-color="#dcefff"/><stop offset="1" stop-color="#e2f8ee"/></linearGradient>'
            '<radialGradient id="dot"><stop offset="0" stop-color="#ffffff"/><stop offset=".55" stop-color="#c4b5fd"/>'
            '<stop offset="1" stop-color="#7c6cf6"/></radialGradient>'
            '<linearGradient id="ln" x1="0" x2="1"><stop offset="0" stop-color="#a5b4fc"/>'
            '<stop offset="1" stop-color="#f0abfc"/></linearGradient>'
            '<radialGradient id="glow" cx=".72" cy=".5" r=".5"><stop offset="0" stop-color="#ffffff" stop-opacity=".9"/>'
            '<stop offset="1" stop-color="#ffffff" stop-opacity="0"/></radialGradient></defs>'
            f'<rect width="{W}" height="{H}" fill="url(#bg)"/>{grid}<rect width="{W}" height="{H}" fill="url(#glow)"/>'
            f'{"".join(lines)}{dots}{"".join(texts) if with_text else ""}</svg>')
