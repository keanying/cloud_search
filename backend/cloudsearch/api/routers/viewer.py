"""右侧只读阅览。接口只读取已有帧与脱敏元数据；没有导航/点击/刷新源页等任何控制参数。"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import get_settings
from ...core.ids import utcnow
from ...core.storage import get_storage
from ...db.base import get_session
from ...db.models import BrowserSession, Task
from ..deps import CurrentUser, current_user
from ..schemas import ViewerMetaOut

router = APIRouter(prefix="/browser-sessions", tags=["viewer"])


async def _session(s: AsyncSession, u: CurrentUser, bsid: str) -> tuple[BrowserSession, Task]:
    bs = await s.get(BrowserSession, bsid)
    task = await s.get(Task, bs.task_id) if bs else None
    if bs is None or task is None or bs.project_id != u.project_id or (
            task.created_by_id != u.user_id and not u.is_admin):
        raise HTTPException(404, "阅览会话不存在或无权限")
    return bs, task


@router.get("/{browser_session_id}/viewer-meta", response_model=ViewerMetaOut)
async def viewer_meta(browser_session_id: str, u: CurrentUser = Depends(current_user),
                      s: AsyncSession = Depends(get_session)):
    bs, task = await _session(s, u, browser_session_id)
    active = bs.session_status == "active"
    stale_after = timedelta(seconds=get_settings().browser_frame_interval_s * 3 + 10)
    stale = bs.frame_time is None or (active and utcnow() - bs.frame_time > stale_after) or not active
    return ViewerMetaOut(browser_session_id=bs.browser_session_id, task_id=bs.task_id, session_label=bs.session_label,
                         session_status=bs.session_status, current_url=bs.current_url, current_title=bs.current_title,
                         current_activity=bs.current_activity, frame_seq_no=bs.frame_seq_no, frame_time=bs.frame_time,
                         connected=active, stale=stale, masked=bs.frame_masked, task_status=task.task_status)


@router.get("/{browser_session_id}/viewer-snapshot")
async def viewer_snapshot(browser_session_id: str, u: CurrentUser = Depends(current_user),
                          s: AsyncSession = Depends(get_session)):
    bs, _ = await _session(s, u, browser_session_id)
    if bs.frame_masked or not bs.frame_ref:
        raise HTTPException(404, "暂无可显示的画面")
    data = await get_storage().get(bs.frame_ref)
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store", "X-Frame-Seq": str(bs.frame_seq_no)})
