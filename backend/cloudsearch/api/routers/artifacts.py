from __future__ import annotations

import csv
import io
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.storage import get_storage
from ...db.base import get_session
from ...db.models import Artifact, Task
from ..deps import CurrentUser, current_user
from ..schemas import ArtifactOut, ArtifactPreviewOut

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

PREVIEW_ROWS = 100


def _out(a: Artifact, t: Task | None) -> ArtifactOut:
    return ArtifactOut(artifact_id=a.artifact_id, task_id=a.task_id, conversation_id=t.conversation_id if t else None,
                       artifact_kind=a.artifact_kind, display_name=a.display_name, mime_name=a.mime_name,
                       byte_qty=a.byte_qty, record_qty=a.record_qty, content_hash=a.content_hash,
                       quality_status=a.quality_status, artifact_status=a.artifact_status, created_time=a.created_time)


async def _get(s: AsyncSession, u: CurrentUser, artifact_id: str) -> tuple[Artifact, Task | None]:
    a = await s.get(Artifact, artifact_id)
    t = await s.get(Task, a.task_id) if a and a.task_id else None
    if a is None or a.project_id != u.project_id or (t and t.created_by_id != u.user_id and not u.is_admin):
        raise HTTPException(404, "文件不存在")
    if a.artifact_status != "available":
        raise HTTPException(410, "文件已不可用")
    return a, t


@router.get("", response_model=list[ArtifactOut])
async def list_artifacts(kind: str | None = None, limit: int = Query(100, le=500),
                         u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    stmt = (select(Artifact, Task).join(Task, Task.task_id == Artifact.task_id)
            .where(Artifact.project_id == u.project_id, Task.created_by_id == u.user_id,
                   Artifact.artifact_status == "available"))
    if kind:
        stmt = stmt.where(Artifact.artifact_kind == kind)
    rows = (await s.execute(stmt.order_by(Artifact.created_time.desc()).limit(limit))).all()
    return [_out(a, t) for a, t in rows]


@router.get("/{artifact_id}", response_model=ArtifactOut)
async def get_artifact(artifact_id: str, u: CurrentUser = Depends(current_user),
                       s: AsyncSession = Depends(get_session)):
    return _out(*await _get(s, u, artifact_id))


@router.get("/{artifact_id}/preview", response_model=ArtifactPreviewOut)
async def preview(artifact_id: str, u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    a, _ = await _get(s, u, artifact_id)
    data = await get_storage().get(a.storage_ref)
    if a.mime_name == "text/csv":
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        body = rows[1:]
        return ArtifactPreviewOut(kind="table", columns=rows[0] if rows else [], rows=body[:PREVIEW_ROWS],
                                  total_rows=len(body), shown_rows=min(len(body), PREVIEW_ROWS))
    if a.mime_name.endswith("spreadsheetml.sheet"):
        from openpyxl import load_workbook

        ws = load_workbook(io.BytesIO(data), read_only=True).worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        body = rows[1:]
        return ArtifactPreviewOut(kind="table", columns=[str(c) for c in rows[0]] if rows else [],
                                  rows=body[:PREVIEW_ROWS], total_rows=len(body),
                                  shown_rows=min(len(body), PREVIEW_ROWS))
    if a.mime_name == "application/pdf" or a.mime_name.endswith("wordprocessingml.document"):
        # 二进制文档：改为预览同一成果的 HTML 版本（同任务同名）
        html_row = (await s.execute(select(Artifact).where(
            Artifact.task_id == a.task_id, Artifact.mime_name == "text/html",
            Artifact.display_name == a.display_name.rsplit(".", 1)[0] + ".html"))).scalar()
        if html_row is None:
            raise HTTPException(415, "该文件不支持在线预览，请下载查看")
        data, a = await get_storage().get(html_row.storage_ref), html_row
    text = data.decode("utf-8", "replace")
    kind = {"text/markdown": "markdown", "text/html": "html"}.get(a.mime_name, "text")
    return ArtifactPreviewOut(kind=kind, content=text[:2_000_000])


@router.get("/{artifact_id}/download")
async def download(artifact_id: str, u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    a, _ = await _get(s, u, artifact_id)
    data = await get_storage().get(a.storage_ref)
    return Response(content=data, media_type=a.mime_name, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(a.display_name)}",
        "X-Content-SHA256": a.content_hash, "Cache-Control": "no-store"})
