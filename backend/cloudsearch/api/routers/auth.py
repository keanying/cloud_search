from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import get_settings
from ...core.ids import new_id
from ...core.security import create_access_token, hash_password, verify_password
from ...db.base import get_session
from ...db.models import Project, ProjectMember, User
from ..deps import CurrentUser, current_user
from ..schemas import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


async def _default_project(s: AsyncSession, user_id: str) -> str | None:
    row = (await s.execute(select(ProjectMember.project_id).where(
        ProjectMember.user_id == user_id, ProjectMember.member_status == "active")
        .order_by(ProjectMember.created_time).limit(1))).scalar()
    return row


def _user_out(u: User, project_id: str) -> UserOut:
    return UserOut(user_id=u.user_id, username=u.username, display_name=u.display_name, is_admin=u.is_admin,
                   project_id=project_id)


@router.post("/register", response_model=TokenOut, status_code=201)
async def register(body: RegisterIn, s: AsyncSession = Depends(get_session)):
    first = (await s.execute(select(func.count()).select_from(User))).scalar_one() == 0
    if not first and not get_settings().allow_registration:
        raise HTTPException(403, "当前不开放注册")
    if (await s.execute(select(User).where(User.username == body.username))).scalar():
        raise HTTPException(409, "用户名已存在")
    user = User(user_id=new_id("usr"), username=body.username, password_hash=hash_password(body.password),
                display_name=body.display_name, is_admin=first)  # 第一个注册用户为平台管理员
    project = Project(project_id=new_id("prj"), project_name=f"{body.display_name or body.username}的空间",
                      owner_user_id=user.user_id)
    s.add_all([user, project, ProjectMember(project_id=project.project_id, user_id=user.user_id,
                                            role_type="admin" if first else "operator")])
    await s.flush()
    return TokenOut(access_token=create_access_token(user.user_id, project.project_id),
                    user=_user_out(user, project.project_id))


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, s: AsyncSession = Depends(get_session)):
    user = (await s.execute(select(User).where(User.username == body.username))).scalar()
    if user is None or not verify_password(body.password, user.password_hash) or user.user_status != "active":
        raise HTTPException(401, "用户名或密码错误")
    project_id = await _default_project(s, user.user_id)
    if project_id is None:
        raise HTTPException(403, "账号没有可用项目")
    return TokenOut(access_token=create_access_token(user.user_id, project_id), user=_user_out(user, project_id))


@router.get("/me", response_model=UserOut)
async def me(u: CurrentUser = Depends(current_user), s: AsyncSession = Depends(get_session)):
    return _user_out(await s.get(User, u.user_id), u.project_id)
