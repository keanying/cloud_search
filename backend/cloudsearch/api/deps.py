from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import decode_access_token
from ..db.base import get_session
from ..db.models import Conversation, ProjectMember, Task, User


@dataclass
class CurrentUser:
    user_id: str
    project_id: str
    is_admin: bool
    role_type: str


async def current_user(authorization: str | None = Header(default=None),
                       s: AsyncSession = Depends(get_session)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "未登录")
    try:
        payload = decode_access_token(authorization.split(" ", 1)[1])
    except jwt.PyJWTError:
        raise HTTPException(401, "登录已失效，请重新登录") from None
    user = await s.get(User, payload["sub"])
    if user is None or user.user_status != "active":
        raise HTTPException(401, "账号不可用")
    member = await s.get(ProjectMember, (payload["prj"], user.user_id))
    if member is None or member.member_status != "active":
        raise HTTPException(403, "无项目权限")
    return CurrentUser(user.user_id, payload["prj"], user.is_admin, member.role_type)


async def admin_user(u: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not u.is_admin:
        raise HTTPException(403, "需要管理员权限")
    return u


async def get_conversation(s: AsyncSession, u: CurrentUser, conversation_id: str) -> Conversation:
    c = await s.get(Conversation, conversation_id)
    # 跨项目/他人会话一律 404，不泄露存在性
    if c is None or c.project_id != u.project_id or c.user_id != u.user_id or c.conversation_status == "deleted":
        raise HTTPException(404, "会话不存在")
    return c


async def get_task(s: AsyncSession, u: CurrentUser, task_id: str) -> Task:
    t = await s.get(Task, task_id)
    if t is None or t.project_id != u.project_id or (t.created_by_id != u.user_id and not u.is_admin):
        raise HTTPException(404, "任务不存在")
    return t
