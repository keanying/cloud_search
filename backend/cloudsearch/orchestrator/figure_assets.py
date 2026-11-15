"""报告配图的生成与下载：阶段总览图、结构示意图（SVG），以及来源网页里的图片（下载后存入私有存储）。

来源图片：只下载撰写智能体选中的、证据中列出的图片；每一跳重定向都经过出口检查（禁止内网地址），
只接受 JPEG / PNG / WebP，最大 6MB；失败时该图省略，不影响报告。
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

from ..agents.report_writer import DiagramSpec, PhotoRef, ReportDraft, figure_fence
from ..browser.guard import check_url
from ..core.storage import get_storage
from .figures import layers_svg, stages_svg

log = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 6 * 1024 * 1024
_MAGIC = {b"\xff\xd8\xff": ("image/jpeg", "jpg"), b"\x89PNG\r\n\x1a\n": ("image/png", "png")}


def _sniff(data: bytes) -> tuple[str, str] | None:
    for magic, out in _MAGIC.items():
        if data.startswith(magic):
            return out
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


async def fetch_image(url: str) -> tuple[bytes, str, str] | None:
    """下载图片：返回 (内容, MIME, 扩展名)；不是图片、太大或被出口防护拒绝时返回 None。"""
    try:
        from curl_cffi.requests import AsyncSession

        from ..browser.http_reader import _proxy_for

        cur = url
        async with AsyncSession(impersonate="chrome131") as client:
            for _ in range(5):
                await check_url(cur)
                resp = await client.get(cur, allow_redirects=False, timeout=20, proxy=_proxy_for(cur))
                loc = resp.headers.get("location")
                if resp.status_code in (301, 302, 303, 307, 308) and loc:
                    cur = urljoin(cur, loc)
                    continue
                break
        if resp.status_code != 200 or len(resp.content or b"") > MAX_IMAGE_BYTES:
            return None
        kind = _sniff(resp.content or b"")
        if kind is None or len(resp.content) < 8 * 1024:  # 太小的多半是图标
            return None
        return resp.content, kind[0], kind[1]
    except Exception as e:  # noqa: BLE001
        log.info("figure download failed %s: %s", url, e)
        return None


def _sources_label(ns: list[int]) -> str:
    return "".join(f"[{n}]" for n in sorted(set(ns)))


def stages_fence(draft: ReportDraft) -> str | None:
    if not draft.stages:
        return None
    ns = sorted({n for st in draft.stages for n in st.source_ns})
    title = draft.stages_title or "发展阶段总览"
    svg = stages_svg({"title": title, "stages": [st.model_dump() for st in draft.stages],
                      "note": "阶段之间存在重叠，并非旧技术被新技术完全替代；时间布局不按年份等比例。", "sources": ns})
    return figure_fence("figure", {"kind": "stages", "caption": title, "sources": _sources_label(ns), "svg": svg})


def diagram_fence(d: DiagramSpec) -> str:
    svg = layers_svg({"title": d.title, "layers": [layer.model_dump() for layer in d.layers], "links": d.links,
                      "note": d.note})
    return figure_fence("figure", {"kind": "diagram", "caption": d.title, "sources": _sources_label(d.source_ns),
                                   "svg": svg})


async def photo_fences(task_id: str, photos: list[PhotoRef], images: dict[str, dict]
                       ) -> tuple[dict[str, str], dict[str, tuple[bytes, str]]]:
    """下载选中的来源图片并存储；返回 ({图片编号: 代码块}, {文件名: (内容, MIME)})。"""
    fences, blobs = {}, {}
    storage = get_storage()
    for p in photos:
        img = images.get(p.image_id)
        if not img:
            continue
        got = await fetch_image(img["url"])
        if got is None:
            continue
        data, mime, ext = got
        name = f"photo-{p.image_id}.{ext}"
        await storage.put(f"figures/{task_id}/{name}", data)
        blobs[name] = (data, mime)
        n = int(p.image_id.split("-")[0])
        credit = f"图片出处：{img.get('site') or '来源网页'}[{n}]"
        fences[p.image_id] = figure_fence("photo", {"task_id": task_id, "name": name, "mime": mime,
                                                    "caption": p.caption, "credit": credit})
    return fences, blobs


async def build_figures(task_id: str, draft: ReportDraft, images: dict[str, dict]
                        ) -> tuple[dict, dict[str, tuple[bytes, str]]]:
    """返回 (assemble_markdown 用的 figures, 导出时内嵌的图片 {文件名: (内容, MIME)})。"""
    photos, blobs = await photo_fences(task_id, draft.photos, images)
    return {"stages": stages_fence(draft), "diagram": {d.id: diagram_fence(d) for d in draft.diagrams},
            "photo": photos}, blobs
