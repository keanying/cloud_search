"""上传文件服务：入库、后台解析队列、状态推送、分段（长文档拆成多个可引用的来源）。"""

from __future__ import annotations

import logging
import mimetypes
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.ids import new_id, utcnow
from ..core.storage import get_storage
from ..db.base import is_mysql, session_scope
from ..db.models import Message, UploadedFile
from ..services.events import append_conversation_event, publish_message, upsert_part
from .parsers import ALLOWED_EXT, PARSER_LABELS, ParseError, parse_bytes

log = logging.getLogger(__name__)
LEASE_S = 120

STATUS_LABELS = {"queued": "排队解析", "parsing": "解析中", "parsed": "已解析", "failed": "解析失败"}


def ext_of(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


def file_out(f: UploadedFile) -> dict[str, Any]:
    return {"file_id": f.file_id, "conversation_id": f.conversation_id, "message_id": f.message_id,
            "name": f.display_name, "mime": f.mime_name, "ext": f.ext_name, "byte_qty": f.byte_qty,
            "parse_status": f.parse_status, "parse_status_label": STATUS_LABELS.get(f.parse_status, f.parse_status),
            "parser": f.parser_name, "parse_detail": f.parse_detail, "parse_error": f.parse_error,
            "page_qty": f.page_qty, "char_qty": f.char_qty, "table_qty": f.table_qty, "image_qty": f.image_qty,
            "outline": f.outline or [], "created_time": f.created_time.isoformat() if f.created_time else None}


def file_part(f: UploadedFile) -> dict[str, Any]:
    """用户消息里的附件片段（随解析状态更新）。"""
    return {"type": "file", "part_id": f"file-{f.file_id}", "file_id": f.file_id, "name": f.display_name,
            "ext": f.ext_name, "byte_qty": f.byte_qty, "parse_status": f.parse_status,
            "parse_detail": f.parse_detail, "parse_error": f.parse_error, "page_qty": f.page_qty}


class UploadRejected(Exception):
    pass


async def create_upload(s: AsyncSession, *, project_id: str, user_id: str, conversation_id: str, name: str,
                        data: bytes, mime: str | None) -> UploadedFile:
    st = get_settings()
    name = Path(name or "file").name[:200] or "file"
    ext = ext_of(name)
    if ext not in ALLOWED_EXT:
        raise UploadRejected(f"不支持的文件类型 .{ext or '?'}；支持 PDF、Word、Excel/CSV、PPT、图片、TXT/Markdown/HTML 等")
    if not data:
        raise UploadRejected("文件是空的")
    if len(data) > st.files_max_mb * 1024 * 1024:
        raise UploadRejected(f"文件超过 {st.files_max_mb}MB 上限")
    fid = new_id("file")
    ref, digest = await get_storage().put(f"files/{project_id}/{fid}/original.{ext}", data)
    f = UploadedFile(file_id=fid, project_id=project_id, user_id=user_id, conversation_id=conversation_id,
                     display_name=name, mime_name=(mime or mimetypes.guess_type(name)[0] or "application/octet-stream")[:128],
                     ext_name=ext[:16], byte_qty=len(data), content_hash=digest, storage_ref=ref,
                     parse_status="queued", attempt_qty=0, file_status="active")
    s.add(f)
    await s.flush()
    await _publish(s, f)
    return f


async def _publish(s: AsyncSession, f: UploadedFile) -> None:
    """推送文件状态：会话事件 + 已发送消息里的附件片段。"""
    if f.conversation_id:
        await append_conversation_event(s, f.conversation_id, "file_updated", file_out(f))
    if f.message_id:
        m = await s.get(Message, f.message_id)
        if m is not None:
            m.parts = upsert_part(list(m.parts or []), file_part(f))
            await publish_message(s, m)


# ---------------------------------------------------------------- 后台解析
async def claim_parse(worker_id: str) -> str | None:
    now = utcnow()
    async with session_scope() as s:
        q = (select(UploadedFile).where(UploadedFile.file_status == "active", or_(
            UploadedFile.parse_status == "queued",
            (UploadedFile.parse_status == "parsing") & (UploadedFile.lease_expire_time < now)))
             .order_by(UploadedFile.created_time).limit(1))
        if is_mysql():
            q = q.with_for_update(skip_locked=True)
        f = (await s.execute(q)).scalar()
        if f is None:
            return None
        if f.attempt_qty >= 3:
            f.parse_status, f.parse_error = "failed", "多次解析中断，已放弃（可删除后重新上传）"
            await _publish(s, f)
            return None
        f.parse_status, f.worker_id = "parsing", worker_id
        f.lease_expire_time = now + timedelta(seconds=max(LEASE_S, get_settings().files_parse_timeout_s + 60))
        f.attempt_qty += 1
        await _publish(s, f)
        return f.file_id


def outline_of(md: str, limit: int = 40) -> list[str]:
    out = []
    for m in re.finditer(r"^(#{1,4})\s+(.+?)\s*#*$", md, re.M):
        out.append(("  " * (len(m.group(1)) - 1)) + m.group(2).strip()[:80])
        if len(out) >= limit:
            break
    return out


async def process_parse(file_id: str, worker_id: str) -> None:
    async with session_scope() as s:
        f = await s.get(UploadedFile, file_id)
        if f is None or f.worker_id != worker_id:
            return
        ref, name, ext, project_id = f.storage_ref, f.display_name, f.ext_name, f.project_id
    storage = get_storage()
    try:
        data = await storage.get(ref)
        res = await parse_bytes(data, name, ext, data_id=file_id)
        md = res.markdown.strip()
        if res.notes:
            md = "> 解析说明：" + "；".join(res.notes) + "\n\n" + md
        md_ref, _ = await storage.put(f"files/{project_id}/{file_id}/parsed.md", md.encode("utf-8"))
        error = None
    except ParseError as e:
        res, md, md_ref, error = None, "", None, str(e)
    except Exception as e:  # noqa: BLE001
        log.exception("parse %s failed", file_id)
        res, md, md_ref, error = None, "", None, f"解析出错：{type(e).__name__}"
    async with session_scope() as s:
        f = await s.get(UploadedFile, file_id)
        if f is None or f.worker_id != worker_id:
            return
        f.lease_expire_time = None
        if error:
            f.parse_status, f.parse_error = "failed", error[:2000]
        else:
            f.parse_status, f.parse_error = "parsed", None
            f.parser_name = res.parser
            f.parse_detail = (res.detail or PARSER_LABELS.get(res.parser, res.parser))[:256]
            f.markdown_ref = md_ref
            f.page_qty = res.page_qty
            f.char_qty = len(md)
            f.table_qty = len(re.findall(r"^\|?\s*-{3,}", md, re.M)) + md.count("<table")
            f.image_qty = res.image_qty
            f.outline = outline_of(md)
            f.preview_text = re.sub(r"\s+", " ", md)[:600]
        await _publish(s, f)


# ---------------------------------------------------------------- 给智能体用
async def load_markdown(f: UploadedFile) -> str:
    return (await get_storage().get(f.markdown_ref)).decode("utf-8") if f.markdown_ref else ""


def segments(md: str, max_chars: int = 14000) -> list[tuple[str, str]]:
    """把长文档按标题/页码切成若干段（每段一个可引用的来源）。返回 [(段标签, 文本)]。"""
    if len(md) <= max_chars:
        return [("", md)]
    cuts = [m.start() for m in re.finditer(r"^(#{1,3}\s+.+|〔第 \d+ 页〕)$", md, re.M)]
    blocks: list[str] = []
    prev = 0
    for c in cuts + [len(md)]:
        if c > prev:
            blocks.append(md[prev:c])
        prev = c
    out: list[tuple[str, str]] = []
    buf = ""
    for b in blocks:
        while len(b) > max_chars:  # 单个超长节：硬切
            if buf:
                out.append(buf)
                buf = ""
            out.append(b[:max_chars])
            b = b[max_chars:]
        if buf and len(buf) + len(b) > max_chars:
            out.append(buf)
            buf = b
        else:
            buf += b
    if buf.strip():
        out.append(buf)

    def label(text: str, i: int) -> str:
        h = re.search(r"^#{1,3}\s+(.+)$", text, re.M)
        p = re.findall(r"〔第 (\d+) 页〕", text)
        if p:
            return f"第 {p[0]}–{p[-1]} 页" if p[0] != p[-1] else f"第 {p[0]} 页"
        return f"第 {i} 部分" + (f"：{h.group(1).strip()[:30]}" if h else "")

    return [(label(t, i), t) for i, t in enumerate(out, 1)]


def describe_for_compiler(files: list[UploadedFile]) -> str:
    """给需求编译智能体看的附件清单。"""
    lines = []
    for f in files:
        meta = [f"{f.byte_qty // 1024 + 1}KB"]
        if f.page_qty:
            meta.append(f"{f.page_qty} 页")
        status = STATUS_LABELS.get(f.parse_status, f.parse_status)
        line = f"- [{f.file_id}] {f.display_name}（{'，'.join(meta)}，{status}）"
        if f.parse_status == "parsed":
            if f.outline:
                line += "\n  大纲：" + "；".join(o.strip() for o in f.outline[:12])
            if f.preview_text:
                line += f"\n  开头：{f.preview_text[:300]}"
        elif f.parse_status == "failed":
            line += f"\n  失败原因：{(f.parse_error or '')[:120]}"
        lines.append(line)
    return "\n".join(lines)
