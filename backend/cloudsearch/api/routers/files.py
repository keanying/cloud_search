"""上传文件：对话附件的上传、查询、预览、下载、重新解析、删除。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import get_settings
from ...core.storage import get_storage
from ...db.base import get_session
from ...db.models import UploadedFile
from ...files.service import UploadRejected, _publish, create_upload, file_out, load_markdown
from ..deps import CurrentUser, current_user, get_conversation

router = APIRouter(tags=["files"])


async def _own(s: AsyncSession, u: CurrentUser, file_id: str) -> UploadedFile:
    f = await s.get(UploadedFile, file_id)
    if f is None or f.file_status != "active" or f.project_id != u.project_id or \
            (f.user_id != u.user_id and not u.is_admin):
        raise HTTPException(404, "文件不存在")
    return f


@router.post("/conversations/{conversation_id}/files", status_code=201)
async def upload(conversation_id: str, files: list[UploadFile] = File(...), u: CurrentUser = Depends(current_user),
                 s: AsyncSession = Depends(get_session)) -> list[dict]:
    c = await get_conversation(s, u, conversation_id)
    st = get_settings()
    if len(files) > st.files_max_per_message:
        raise HTTPException(422, f"一次最多上传 {st.files_max_per_message} 个文件")
    out = []
    for up in files:
        data = await up.read(st.files_max_mb * 1024 * 1024 + 1)
        try:
            f = await create_upload(s, project_id=c.project_id, user_id=u.user_id, conversation_id=conversation_id,
                                    name=up.filename or "file", data=data, mime=up.content_type)
        except UploadRejected as e:
            raise HTTPException(422, f"{up.filename}：{e}") from None
        out.append(file_out(f))
    await s.commit()
    return out


@router.get("/conversations/{conversation_id}/files")
async def list_files(conversation_id: str, u: CurrentUser = Depends(current_user),
                     s: AsyncSession = Depends(get_session)) -> list[dict]:
    await get_conversation(s, u, conversation_id)
    rows = (await s.execute(select(UploadedFile).where(UploadedFile.conversation_id == conversation_id,
                                                       UploadedFile.file_status == "active")
                            .order_by(UploadedFile.created_time))).scalars().all()
    return [file_out(f) for f in rows]


@router.get("/files/{file_id}")
async def get_file(file_id: str, u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    return file_out(await _own(s, u, file_id))


@router.get("/files/{file_id}/content")
async def file_content(file_id: str, u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    """解析后的 Markdown（预览用，最多 30 万字）。"""
    f = await _own(s, u, file_id)
    if f.parse_status != "parsed":
        raise HTTPException(409, "文件还没有解析完成" if f.parse_status != "failed" else f"解析失败：{f.parse_error}")
    md = await load_markdown(f)
    return {"file": file_out(f), "markdown": md[:300000], "truncated": len(md) > 300000}


@router.get("/files/{file_id}/download")
async def download(file_id: str, u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    f = await _own(s, u, file_id)
    data = await get_storage().get(f.storage_ref)
    return Response(data, media_type=f.mime_name,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(f.display_name)}"})


@router.post("/files/{file_id}/reparse")
async def reparse(file_id: str, u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    """重新解析（例如管理员配置 MinerU 之后）。"""
    f = await _own(s, u, file_id)
    if f.parse_status in ("queued", "parsing"):
        raise HTTPException(409, "正在解析中")
    f.parse_status, f.parse_error, f.attempt_qty, f.worker_id = "queued", None, 0, None
    await _publish(s, f)
    await s.commit()
    return file_out(f)


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(file_id: str, u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    f = await _own(s, u, file_id)
    if f.message_id:
        raise HTTPException(409, "文件已随消息发送，不能删除")
    f.file_status = "deleted"
    await s.commit()
    return Response(status_code=204)
