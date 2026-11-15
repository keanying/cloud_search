"""调试日志导出（仅管理员）：把一个任务或一段时间内整个系统的详细记录打成 ZIP 下载，用于分析问题。

包含：执行日志、每个步骤的输入输出（各智能体解析出的结构化内容）、模型调用记录、详细调试记录（开启时：
完整提示词与模型输出、各引擎完整搜索结果、网页/文件解析正文片段）、搜索候选、已读来源（可含正文）、证据、
成果、对话消息、浏览器会话、人机验证截图、系统日志与错误汇总、配置摘要（不含任何密钥与密码）。
"""

from __future__ import annotations

import json
import platform
import re
import tempfile
import zipfile
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import runtime
from ...core.config import get_settings
from ...core.ids import utcnow
from ...core.storage import get_storage
from ...core.tracelog import config_summary, debug_dir, debug_enabled, logs_dir, trace_path
from ...db.base import get_session
from ...db.models import (
    AgentModelBinding,
    AgentRun,
    Artifact,
    BrowserSession,
    Evidence,
    LlmModel,
    LlmProvider,
    Message,
    SourceCandidate,
    SourceRevision,
    SystemSetting,
    Task,
    TaskEvent,
    TaskRun,
    TaskStep,
    UploadedFile,
)
from ..deps import CurrentUser, admin_user

router = APIRouter(prefix="/admin/debug", tags=["admin"])

MAX_TASKS = 30  # 全系统导出时最多包含的任务数（最近的优先）
MAX_TEXT_BYTES = 300_000  # 每个来源/文件正文最多导出的字节数
MAX_APP_LOG_BYTES = 30 * 1024 * 1024
SECRET_COLUMNS = {"api_key_cipher", "password_hash", "token_hash"}

README = """# 云搜浏览器 · 调试日志包

导出时间：{now}　范围：{scope}　含正文：{text}　详细调试记录：{debug}

## 目录
- `system/`：系统信息
  - `config.json`：配置摘要、在线参数、模型供应商与模型（不含密钥）、智能体分工、依赖版本、引擎健康状态
  - `errors.json`：时间范围内失败的任务、步骤与模型调用
  - `app.log*`：全局运行日志（含报错堆栈）
  - `debug/*.jsonl`：详细调试记录（开启“详细调试记录”后才有）。每行一个 JSON，kind 字段：
    llm（智能体调用：完整提示词 instructions/prompt 与输出 output）、search（每个引擎的完整搜索结果 hits）、
    read（网页读取：方式、状态、原因、正文片段 text_excerpt）、file（文件解析：解析器、正文片段）
- `tasks/<任务ID>/`：每个任务
  - `trace.log`：逐行执行日志（步骤耗时、搜索、读取、人机验证判定、模型调用、报错）
  - `task.json` / `runs.json`：任务与每次执行
  - `steps.json`：每个步骤的输入输出（各智能体解析出的结构化内容：需求、搜索词、抽取的事实、核验结果、报告等）与错误
  - `agent_runs.json`：模型调用记录（智能体、模型、token、耗时、费用、错误）
  - `debug.jsonl`：这个任务（及其对话）的详细调试记录
  - `search_candidates.json`：搜索得到的全部候选（查询词、引擎、排名、标题、链接、摘要、状态）
  - `sources.json` / `sources_text/`：已读来源与正文
  - `evidence.json`：抽取的证据与核验状态
  - `artifacts.json`：生成的成果（报告、数据文件）
  - `messages.json`：所在对话的消息（含界面卡片数据）
  - `events.json`：任务事件流
  - `browser_sessions.json`、`challenges/`：浏览器会话与人机验证截图/页面
  - `files.json` / `files_text/`：任务用到的上传文件及解析结果
"""


def _row(r: Any) -> dict:
    return {c.name: getattr(r, c.key) for c in r.__table__.columns if c.name not in SECRET_COLUMNS}


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name)[:60] or "x"


def _versions() -> dict:
    from importlib import metadata

    out = {"python": platform.python_version(), "platform": platform.platform()}
    for pkg in ("fastapi", "sqlalchemy", "pydantic-ai-slim", "pydantic-ai", "playwright", "duckduckgo-mcp-server",
                "ddgs", "curl_cffi", "trafilatura", "pypdf"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            pass
    try:
        from .tasks import _git_version

        out["git"] = _git_version()
    except Exception:  # noqa: BLE001
        pass
    return out


def _engine_health() -> dict:
    import time

    from ...search.service import health

    now = time.monotonic()
    return {k: f"冷却中，还剩 {int(v - now)} 秒" for k, v in health._blocked_until.items() if v > now}


def _debug_rows(match, since: datetime | None = None) -> list[str]:
    """从 logs/debug/*.jsonl 里挑出满足条件的行。"""
    out: list[str] = []
    d = debug_dir()
    if not d.exists():
        return out
    for f in sorted(d.glob("*.jsonl")):
        if since and datetime.fromtimestamp(f.stat().st_mtime) < since - timedelta(days=1):
            continue
        with f.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if match(row):
                    out.append(line.rstrip("\n"))
    return out


async def _text(ref: str | None) -> str | None:
    if not ref:
        return None
    try:
        data = await get_storage().get(ref)
    except Exception as e:  # noqa: BLE001
        return f"（读取失败：{type(e).__name__}）"
    cut = data[:MAX_TEXT_BYTES].decode("utf-8", errors="replace")
    return cut + ("\n\n…（已截断）" if len(data) > MAX_TEXT_BYTES else "")


async def _add_task(z: zipfile.ZipFile, s: AsyncSession, t: Task, include_text: bool) -> None:
    base = f"tasks/{t.task_id}_{_safe(t.title)}/"

    async def rows(model, *where, order=None, limit: int | None = None) -> list:
        stmt = select(model).where(*where)
        if order is not None:
            stmt = stmt.order_by(order)
        if limit:
            stmt = stmt.limit(limit)
        return list((await s.execute(stmt)).scalars())

    z.writestr(base + "task.json", _json(_row(t)))
    p = trace_path(t.task_id)
    if p.exists():
        z.write(p, base + "trace.log")
    z.writestr(base + "runs.json", _json([_row(r) for r in await rows(TaskRun, TaskRun.task_id == t.task_id,
                                                                       order=TaskRun.run_seq_no)]))
    z.writestr(base + "steps.json", _json([_row(r) for r in await rows(TaskStep, TaskStep.task_id == t.task_id,
                                                                        order=TaskStep.created_time)]))
    z.writestr(base + "agent_runs.json", _json([_row(r) for r in await rows(AgentRun, AgentRun.task_id == t.task_id,
                                                                             order=AgentRun.started_time)]))
    z.writestr(base + "events.json", _json([_row(r) for r in await rows(TaskEvent, TaskEvent.task_id == t.task_id,
                                                                         order=TaskEvent.event_seq_no, limit=5000)]))
    z.writestr(base + "search_candidates.json", _json([_row(r) for r in await rows(
        SourceCandidate, SourceCandidate.task_id == t.task_id, order=SourceCandidate.created_time)]))
    sources = await rows(SourceRevision, SourceRevision.task_id == t.task_id, order=SourceRevision.retrieved_time)
    z.writestr(base + "sources.json", _json([_row(r) for r in sources]))
    if include_text:
        for r in sources:
            txt = await _text(r.content_ref)
            if txt:
                z.writestr(base + f"sources_text/{r.source_no or 0:03d}_{_safe(r.title or r.final_url or '')}.txt",
                           f"{r.title}\n{r.final_url}\n{'=' * 60}\n{txt}")
    z.writestr(base + "evidence.json", _json([_row(r) for r in await rows(Evidence, Evidence.task_id == t.task_id)]))
    z.writestr(base + "artifacts.json", _json([_row(r) for r in await rows(Artifact, Artifact.task_id == t.task_id)]))
    z.writestr(base + "browser_sessions.json", _json([_row(r) for r in await rows(
        BrowserSession, BrowserSession.task_id == t.task_id)]))
    if t.conversation_id:
        z.writestr(base + "messages.json", _json([_row(r) for r in await rows(
            Message, Message.conversation_id == t.conversation_id, order=Message.created_time)]))
    file_ids = ((t.task_spec or {}).get("scope") or {}).get("file_ids") or []
    if file_ids:
        files = await rows(UploadedFile, UploadedFile.file_id.in_(file_ids))
        z.writestr(base + "files.json", _json([_row(f) for f in files]))
        if include_text:
            for f in files:
                txt = await _text(f.markdown_ref)
                if txt:
                    z.writestr(base + f"files_text/{_safe(f.display_name)}.md", txt)
    dbg = _debug_rows(lambda r: r.get("task_id") == t.task_id or
                      (t.conversation_id and r.get("conversation_id") == t.conversation_id and not r.get("task_id")))
    if dbg:
        z.writestr(base + "debug.jsonl", "\n".join(dbg) + "\n")
    ch = logs_dir() / "challenges"
    if ch.exists():
        for f in ch.glob(f"*_{t.task_id}_*"):
            z.write(f, base + "challenges/" + f.name)


async def _add_system(z: zipfile.ZipFile, s: AsyncSession, since: datetime | None, full: bool) -> None:
    overrides = {r.setting_key: r.setting_value for r in (await s.execute(select(SystemSetting))).scalars()}
    providers = [_row(r) for r in (await s.execute(select(LlmProvider))).scalars()]
    models = [_row(r) for r in (await s.execute(select(LlmModel))).scalars()]
    bindings = [_row(r) for r in (await s.execute(select(AgentModelBinding))).scalars()]
    z.writestr("system/config.json", _json({
        "config_summary": config_summary(),
        "runtime_overrides": {k: v for k, v in overrides.items() if k in runtime.BY_KEY},
        "llm_providers": providers, "llm_models": models, "agent_bindings": bindings,
        "versions": _versions(), "engine_health_api_process": _engine_health(),
    }))
    if not full:
        return
    window = [Task.updated_time >= since] if since else []
    failed_tasks = (await s.execute(select(Task).where(
        Task.task_status.in_(("failed", "partial_failed")), *window))).scalars()
    failed_steps = (await s.execute(select(TaskStep).where(
        TaskStep.step_status == "failed", *([TaskStep.created_time >= since] if since else [])))).scalars()
    failed_llm = (await s.execute(select(AgentRun).where(
        AgentRun.run_status != "succeeded", *([AgentRun.started_time >= since] if since else [])))).scalars()
    z.writestr("system/errors.json", _json({
        "failed_tasks": [{k: v for k, v in _row(t).items() if k not in ("task_spec", "result_summary")}
                         for t in failed_tasks],
        "failed_steps": [_row(r) for r in failed_steps],
        "failed_llm_calls": [_row(r) for r in failed_llm],
    }))
    # 全局日志：从最新的往前取，总量有上限
    total = 0
    for f in sorted(logs_dir().glob("app.log*"), key=lambda p: p.stat().st_mtime, reverse=True):
        size = f.stat().st_size
        if total + size > MAX_APP_LOG_BYTES:
            break
        z.write(f, "system/" + f.name)
        total += size
    d = debug_dir()
    if d.exists():
        for f in sorted(d.glob("*.jsonl")):
            if since is None or datetime.fromtimestamp(f.stat().st_mtime) >= since - timedelta(hours=1):
                z.write(f, "system/debug/" + f.name)


@router.get("/status")
async def debug_status(_: CurrentUser = Depends(admin_user)) -> dict:
    d = debug_dir()
    files = []
    if d.exists():
        for f in sorted(d.glob("*.jsonl"), reverse=True):
            st = f.stat()
            files.append({"name": f.name, "bytes": st.st_size,
                          "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")})
    app_bytes = sum(p.stat().st_size for p in logs_dir().glob("app.log*"))
    ch = logs_dir() / "challenges"
    return {"enabled": debug_enabled(), "keep_days": get_settings().logs_debug_keep_days, "files": files,
            "app_log_bytes": app_bytes, "challenge_files": len(list(ch.glob("*"))) if ch.exists() else 0,
            "logs_dir": str(logs_dir())}


@router.get("/bundle")
async def debug_bundle(task_id: str | None = None, hours: int = Query(24, ge=1, le=24 * 30),
                       include_text: bool = True, _: CurrentUser = Depends(admin_user),
                       s: AsyncSession = Depends(get_session)) -> StreamingResponse:
    """task_id：只导出这个任务（及系统配置）；否则导出最近 hours 小时内整个系统（含最多 30 个任务）。"""
    now = datetime.now()
    if task_id:
        t = await s.get(Task, task_id)
        if t is None:
            raise HTTPException(404, "任务不存在")
        tasks, since, scope = [t], None, f"任务 {t.title}（{t.task_id}）"
    else:
        since = utcnow() - timedelta(hours=hours)
        tasks = list((await s.execute(select(Task).where(or_(Task.created_time >= since, Task.updated_time >= since))
                                      .order_by(Task.updated_time.desc()).limit(MAX_TASKS))).scalars())
        scope = f"最近 {hours} 小时全系统（{len(tasks)} 个任务）"
    buf = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)  # noqa: SIM115 —— 随响应关闭
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("README.md", README.format(now=f"{now:%Y-%m-%d %H:%M:%S}", scope=scope,
                                              text="是" if include_text else "否",
                                              debug="已开启" if debug_enabled() else "未开启（只有基础记录）"))
        await _add_system(z, s, since, full=not task_id)
        if not task_id:
            # 不属于任何任务的调试记录（如理解需求、澄清）
            rows = _debug_rows(lambda r: not r.get("task_id"), since)
            if rows:
                z.writestr("system/debug_without_task.jsonl", "\n".join(rows) + "\n")
        for t in tasks:
            await _add_task(z, s, t, include_text)
    size = buf.tell()
    buf.seek(0)

    def chunks():
        try:
            while data := buf.read(1024 * 1024):
                yield data
        finally:
            buf.close()

    name = f"调试日志_{'任务_' + _safe(tasks[0].title) if task_id else f'全系统_{hours}小时'}_{now:%Y%m%d-%H%M%S}.zip"
    return StreamingResponse(chunks(), media_type="application/zip", headers={
        "Content-Disposition": f"attachment; filename=debug.zip; filename*=UTF-8''{quote(name)}",
        "Content-Length": str(size)})


__all__ = ["router"]
