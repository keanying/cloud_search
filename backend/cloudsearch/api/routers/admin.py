"""管理后台：概览统计、任务/调用记录/用户列表、运行参数在线修改、搜索引擎检测。"""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...agents.base import ROLE_INFO
from ...core import runtime
from ...core.config import get_settings
from ...core.ids import utcnow
from ...db.base import get_session
from ...db.models import AgentRun, Artifact, Conversation, SourceRevision, SystemSetting, Task, User
from ..deps import CurrentUser, admin_user

router = APIRouter(prefix="/admin", tags=["admin"])

ACTIVE = ("queued", "running", "pausing", "paused", "stopping")
FAILED = ("failed", "partial_failed")


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _page(items: list, total: int, page: int, size: int) -> dict:
    return {"items": items, "total": total, "page": page, "size": size}


async def _count(s: AsyncSession, q) -> int:
    return int((await s.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0)


# ---------------------------------------------------------------- 概览
@router.get("/overview")
async def overview(days: int = Query(14, ge=1, le=90), _: CurrentUser = Depends(admin_user),
                   s: AsyncSession = Depends(get_session)) -> dict:
    since = utcnow() - timedelta(days=days)
    scalar = lambda q: s.execute(q)  # noqa: E731

    totals = {
        "users": (await scalar(select(func.count()).select_from(User))).scalar() or 0,
        "conversations": (await scalar(select(func.count()).select_from(Conversation)
                                       .where(Conversation.conversation_status != "deleted"))).scalar() or 0,
        "tasks": (await scalar(select(func.count()).select_from(Task).where(Task.created_time >= since)
                               .where(Task.task_status != "draft"))).scalar() or 0,
        "tasks_active": (await scalar(select(func.count()).select_from(Task)
                                      .where(Task.task_status.in_(ACTIVE)))).scalar() or 0,
        "artifacts": (await scalar(select(func.count()).select_from(Artifact)
                                   .where(Artifact.created_time >= since))).scalar() or 0,
        "sources_read": (await scalar(select(func.count()).select_from(SourceRevision)
                                      .where(SourceRevision.retrieved_time >= since,
                                             SourceRevision.revision_status == "captured"))).scalar() or 0,
    }
    status_rows = (await s.execute(select(Task.task_status, func.count()).where(Task.created_time >= since)
                                   .group_by(Task.task_status))).all()
    task_status = {st: int(n) for st, n in status_rows}

    # 按天：数据库差异（MySQL 返回 date，SQLite 返回字符串）统一转成 YYYY-MM-DD
    day = func.date(Task.created_time)
    by_day_rows = (await s.execute(select(day, Task.task_status, func.count()).where(
        Task.created_time >= since, Task.task_status != "draft").group_by(day, Task.task_status))).all()
    buckets: dict[str, dict[str, int]] = {}
    for i in range(days):
        d = (utcnow() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        buckets[d] = {"total": 0, "completed": 0, "failed": 0}
    for d, st, n in by_day_rows:
        key = str(d)[:10]
        b = buckets.setdefault(key, {"total": 0, "completed": 0, "failed": 0})
        b["total"] += int(n)
        if st == "completed":
            b["completed"] += int(n)
        elif st in FAILED:
            b["failed"] += int(n)
    tasks_by_day = [{"date": k, **v} for k, v in sorted(buckets.items())]

    runs = (await s.execute(select(AgentRun.agent_role, AgentRun.provider_name, AgentRun.model_name,
                                   AgentRun.request_qty, AgentRun.input_token_qty, AgentRun.output_token_qty,
                                   AgentRun.cost_minor_amt, AgentRun.currency_code, AgentRun.cost_status,
                                   AgentRun.run_status, AgentRun.started_time, AgentRun.finished_time)
                            .where(AgentRun.started_time >= since))).all()
    llm = {"requests": 0, "input_tokens": 0, "output_tokens": 0, "failed_runs": 0, "unknown_cost_runs": 0}
    cost: dict[str, int] = {}
    roles: dict[str, dict[str, Any]] = {}
    models: dict[tuple, dict[str, Any]] = {}
    for r in runs:
        llm["requests"] += r.request_qty or 0
        llm["input_tokens"] += r.input_token_qty or 0
        llm["output_tokens"] += r.output_token_qty or 0
        failed = r.run_status != "succeeded"
        llm["failed_runs"] += failed
        if r.cost_minor_amt is not None and r.currency_code:
            cost[r.currency_code] = cost.get(r.currency_code, 0) + int(r.cost_minor_amt)
        elif r.cost_status == "unknown":
            llm["unknown_cost_runs"] += 1
        ro = roles.setdefault(r.agent_role, {"role": r.agent_role, "label": ROLE_INFO.get(r.agent_role, (r.agent_role,))[0],
                                             "requests": 0, "input_tokens": 0, "output_tokens": 0, "failed": 0,
                                             "_ms": []})
        ro["requests"] += r.request_qty or 0
        ro["input_tokens"] += r.input_token_qty or 0
        ro["output_tokens"] += r.output_token_qty or 0
        ro["failed"] += failed
        if r.finished_time and r.started_time:
            ro["_ms"].append((r.finished_time - r.started_time).total_seconds() * 1000)
        mo = models.setdefault((r.provider_name, r.model_name), {
            "provider_name": r.provider_name, "model_name": r.model_name, "requests": 0, "input_tokens": 0,
            "output_tokens": 0})
        mo["requests"] += r.request_qty or 0
        mo["input_tokens"] += r.input_token_qty or 0
        mo["output_tokens"] += r.output_token_qty or 0
    llm["cost"] = [{"currency_code": c, "minor_amt": v} for c, v in sorted(cost.items())]
    by_role = []
    for ro in roles.values():
        ms = ro.pop("_ms")
        ro["avg_ms"] = int(sum(ms) / len(ms)) if ms else None
        by_role.append(ro)
    order = list(ROLE_INFO)
    by_role.sort(key=lambda x: order.index(x["role"]) if x["role"] in order else 99)

    failures = []
    for t in (await s.execute(select(Task).where(Task.task_status.in_(FAILED), Task.updated_time >= since)
                              .order_by(Task.updated_time.desc()).limit(8))).scalars():
        failures.append({"kind": "task", "id": t.task_id, "title": t.title,
                         "detail": (t.result_summary or {}).get("error_desc") or t.status_reason,
                         "time": _iso(t.updated_time), "conversation_id": t.conversation_id})
    for r in (await s.execute(select(AgentRun).where(AgentRun.run_status != "succeeded",
                                                     AgentRun.started_time >= since)
                              .order_by(AgentRun.started_time.desc()).limit(8))).scalars():
        failures.append({"kind": "agent_run", "id": r.agent_run_id,
                         "title": f"{ROLE_INFO.get(r.agent_role, (r.agent_role,))[0]} · {r.model_name or ''}",
                         "detail": (r.error_desc or "")[:300] or None, "time": _iso(r.started_time),
                         "conversation_id": r.conversation_id})
    failures.sort(key=lambda x: x["time"] or "", reverse=True)

    return {"totals": totals, "task_status": task_status, "tasks_by_day": tasks_by_day, "llm": llm,
            "llm_by_role": by_role,
            "llm_by_model": sorted(models.values(), key=lambda m: -m["requests"]),
            "recent_failures": failures[:10], "engines": _engine_status()}


def _engine_status() -> list[dict]:
    from ...search.service import all_engines, health

    settings = get_settings()
    now = time.monotonic()
    wall = utcnow()
    out = []
    vertical_enabled = settings.search_vertical_sources
    for name, e in all_engines().items():
        cfg = getattr(e, "cfg", None)
        kind = "vertical" if cfg is not None and cfg.kind == "vertical" else "general"
        enabled = name in settings.search_engines if kind == "general" else (
            vertical_enabled is None or name in vertical_enabled)
        until = health._blocked_until.get(name, 0)
        out.append({"name": name, "label": runtime.engine_label(name), "kind": kind, "enabled": enabled,
                    "cooldown_until": _iso(wall + timedelta(seconds=until - now)) if until > now else None})
    order = settings.search_engines
    out.sort(key=lambda x: (x["kind"] != "general", order.index(x["name"]) if x["name"] in order else 99))
    return out


# ---------------------------------------------------------------- 列表
@router.get("/agent-runs")
async def agent_runs(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), role: str | None = None,
                     status: str | None = None, q: str | None = None, _: CurrentUser = Depends(admin_user),
                     s: AsyncSession = Depends(get_session)) -> dict:
    stmt = select(AgentRun)
    if role:
        stmt = stmt.where(AgentRun.agent_role == role)
    if status:
        stmt = stmt.where(AgentRun.run_status == status) if status == "succeeded" else \
            stmt.where(AgentRun.run_status != "succeeded")
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(AgentRun.task_id.like(like), AgentRun.model_name.like(like),
                              AgentRun.provider_name.like(like), AgentRun.conversation_id.like(like)))
    total = await _count(s, stmt)
    rows = (await s.execute(stmt.order_by(AgentRun.started_time.desc()).offset((page - 1) * size).limit(size)
                            )).scalars().all()
    items = [{
        "agent_run_id": r.agent_run_id, "task_id": r.task_id, "conversation_id": r.conversation_id,
        "agent_role": r.agent_role, "role_label": ROLE_INFO.get(r.agent_role, (r.agent_role,))[0],
        "provider_name": r.provider_name, "model_name": r.model_name, "request_qty": r.request_qty,
        "input_token_qty": r.input_token_qty, "output_token_qty": r.output_token_qty,
        "cost_minor_amt": r.cost_minor_amt, "currency_code": r.currency_code, "cost_status": r.cost_status,
        "run_status": r.run_status, "error_desc": r.error_desc, "started_time": _iso(r.started_time),
        "finished_time": _iso(r.finished_time),
        "duration_ms": int((r.finished_time - r.started_time).total_seconds() * 1000)
        if r.finished_time and r.started_time else None} for r in rows]
    return _page(items, total, page, size)


@router.get("/tasks")
async def tasks(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), status: str | None = None,
                mode: str | None = None, q: str | None = None, _: CurrentUser = Depends(admin_user),
                s: AsyncSession = Depends(get_session)) -> dict:
    stmt = select(Task, User).join(User, User.user_id == Task.created_by_id, isouter=True)
    if status == "active":
        stmt = stmt.where(Task.task_status.in_(ACTIVE))
    elif status == "failed":
        stmt = stmt.where(Task.task_status.in_(FAILED))
    elif status:
        stmt = stmt.where(Task.task_status == status)
    if mode:
        stmt = stmt.where(Task.mode == mode)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Task.title.like(like), Task.task_id.like(like), User.username.like(like)))
    total = await _count(s, stmt)
    rows = (await s.execute(stmt.order_by(Task.created_time.desc()).offset((page - 1) * size).limit(size))).all()
    items = [{
        "task_id": t.task_id, "title": t.title, "mode": t.mode, "task_status": t.task_status,
        "status_reason": t.status_reason, "current_stage": t.current_stage,
        "username": u.username if u else None, "display_name": u.display_name if u else None,
        "conversation_id": t.conversation_id, "llm_request_qty": t.llm_request_qty,
        "spent_minor_amt": t.spent_minor_amt, "cost_unknown_qty": t.cost_unknown_qty,
        "created_time": _iso(t.created_time), "updated_time": _iso(t.updated_time)} for t, u in rows]
    return _page(items, total, page, size)


async def _user_item(s: AsyncSession, u: User) -> dict:
    conv = (await s.execute(select(func.count()).select_from(Conversation).where(
        Conversation.user_id == u.user_id, Conversation.conversation_status != "deleted"))).scalar() or 0
    tq = (await s.execute(select(func.count()).select_from(Task).where(
        Task.created_by_id == u.user_id, Task.task_status != "draft"))).scalar() or 0
    return {"user_id": u.user_id, "username": u.username, "display_name": u.display_name, "is_admin": u.is_admin,
            "user_status": u.user_status, "created_time": _iso(u.created_time), "conversation_qty": int(conv),
            "task_qty": int(tq)}


@router.get("/users")
async def users(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), q: str | None = None,
                _: CurrentUser = Depends(admin_user), s: AsyncSession = Depends(get_session)) -> dict:
    stmt = select(User)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.username.like(like), User.display_name.like(like)))
    total = await _count(s, stmt)
    rows = (await s.execute(stmt.order_by(User.created_time.desc()).offset((page - 1) * size).limit(size)
                            )).scalars().all()
    return _page([await _user_item(s, u) for u in rows], total, page, size)


class UserPatch(BaseModel):
    is_admin: bool | None = None
    user_status: str | None = None


@router.patch("/users/{user_id}")
async def patch_user(user_id: str, body: UserPatch, me: CurrentUser = Depends(admin_user),
                     s: AsyncSession = Depends(get_session)) -> dict:
    u = await s.get(User, user_id)
    if u is None:
        raise HTTPException(404, "用户不存在")
    if user_id == me.user_id and (body.is_admin is False or (body.user_status and body.user_status != "active")):
        raise HTTPException(400, "不能取消自己的管理员身份或停用自己的账号")
    if body.user_status is not None:
        if body.user_status not in ("active", "disabled"):
            raise HTTPException(422, "状态只能是 active 或 disabled")
        u.user_status = body.user_status
    if body.is_admin is not None:
        if body.is_admin is False and u.is_admin:
            admins = (await s.execute(select(func.count()).select_from(User).where(
                User.is_admin.is_(True), User.user_status == "active"))).scalar() or 0
            if admins <= 1:
                raise HTTPException(400, "至少需要保留一个管理员")
        u.is_admin = body.is_admin
    await s.commit()
    return await _user_item(s, u)


# ---------------------------------------------------------------- 运行参数
async def _settings_out(s: AsyncSession) -> dict:
    overrides = await runtime.load_overrides(s)
    runtime.apply(overrides)
    from ...core.config import config_file_path

    return {"fields": runtime.describe(overrides), "static": _static_config(), "config_path": str(config_file_path())}


def _static_config() -> list[dict]:
    """只读展示 config.yaml 中需重启生效的项（密钥打码）。"""
    st = get_settings()

    def mask_url(u: str) -> str:
        import re

        return re.sub(r"//([^:/@]+):[^@]+@", r"//\1:****@", u)

    from ...browser.launch import resolve

    try:
        browser = resolve()["detail"]
    except Exception:  # noqa: BLE001
        browser = st.browser_channel
    return [
        {"group": "服务", "items": [
            {"label": "监听地址", "value": f"{st.server_host}:{st.server_port}"},
            {"label": "后台 worker", "value": "内嵌在 Web 进程" if st.embedded_worker
             else f"独立进程 × {st.worker_processes}"},
            {"label": "单个 worker 并行任务", "value": str(st.worker_max_tasks)}]},
        {"group": "数据库", "items": [{"label": "连接", "value": mask_url(st.database_url)}]},
        {"group": "云端浏览器", "items": [
            {"label": "内核", "value": browser},
            {"label": "无头模式", "value": "是" if st.browser_headless else "否（显示窗口）"},
            {"label": "代理", "value": mask_url(st.browser_proxy) if st.browser_proxy else "未设置（直连）"},
            {"label": "语言区域", "value": st.browser_locale}]},
    ]


class SettingsIn(BaseModel):
    values: dict[str, Any]


@router.get("/settings")
async def get_runtime_settings(_: CurrentUser = Depends(admin_user), s: AsyncSession = Depends(get_session)) -> dict:
    return await _settings_out(s)


@router.put("/settings")
async def put_runtime_settings(body: SettingsIn, me: CurrentUser = Depends(admin_user),
                               s: AsyncSession = Depends(get_session)) -> dict:
    clean = {}
    for k, v in body.values.items():
        try:
            clean[k] = runtime.validate(k, v)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
    for k, v in clean.items():
        row = await s.get(SystemSetting, k)
        if row is None:
            s.add(SystemSetting(setting_key=k, setting_value=v, updated_by_id=me.user_id))
        else:
            row.setting_value = v
            row.updated_by_id = me.user_id
            row.updated_time = utcnow()
    await s.commit()
    return await _settings_out(s)


@router.delete("/settings/{key}")
async def reset_runtime_setting(key: str, _: CurrentUser = Depends(admin_user),
                                s: AsyncSession = Depends(get_session)) -> dict:
    if key not in runtime.BY_KEY:
        raise HTTPException(404, "没有这个参数")
    await s.execute(delete(SystemSetting).where(SystemSetting.setting_key == key))
    await s.commit()
    return await _settings_out(s)


# ---------------------------------------------------------------- 搜索引擎检测
class DiagnoseIn(BaseModel):
    query: str = "故宫博物院 开放时间"
    engines: list[str] | None = None


@router.post("/search/diagnose")
async def diagnose(body: DiagnoseIn, _: CurrentUser = Depends(admin_user)) -> dict:
    from ...browser.launch import resolve
    from ...search.diagnose import diagnose_engines

    st = get_settings()
    try:
        browser = resolve()["detail"]
    except Exception:  # noqa: BLE001
        browser = st.browser_channel
    try:
        results = await diagnose_engines(body.query.strip() or "故宫博物院 开放时间", body.engines)
    except Exception as e:  # noqa: BLE001 —— 浏览器无法启动等
        raise HTTPException(503, f"无法启动云端浏览器：{str(e).splitlines()[0][:160]}") from None
    return {"browser": browser, "proxy": st.browser_proxy or None, "results": results}
