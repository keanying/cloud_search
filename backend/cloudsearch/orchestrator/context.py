"""任务执行上下文：栅栏（cancel_generation + lease_epoch）、预算、可复用步骤与带栅栏提交。

- check()：任务被停止/暂停（cancel_generation 变化）或租约被他人接管（lease_epoch 变化）时抛异常，
  阻止新的浏览动作与有价模型请求。
- step()：同一 node_id 已有成功结果则直接复用（暂停后恢复不重复执行、不重复计费）；
  新结果与其持久化写入在同一事务中再次校验栅栏，失败则隔离（late_result_quarantined），不进入正式成果。
"""

from __future__ import annotations

import asyncio
import time
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.ids import new_id, sha256_json, utcnow
from ..db.base import session_scope
from ..db.models import Task, TaskRun, TaskStep

log = logging.getLogger(__name__)


class TaskInterrupted(Exception):
    def __init__(self, kind: str):  # stop / pause
        super().__init__(kind)
        self.kind = kind


class LeaseLost(Exception):
    pass


class BudgetExhausted(Exception):
    pass


@dataclass
class StepResult:
    output: dict[str, Any]
    persist: Callable[[AsyncSession], Awaitable[None]] | None = None


@dataclass
class TaskExecContext:
    task_id: str
    run_id: str
    project_id: str
    worker_id: str
    cancel_generation: int
    lease_epoch: int
    max_llm_requests: int
    budget_limit_minor_amt: int | None = None
    step_id: str | None = None
    lost: bool = False

    def for_step(self, step_id: str) -> TaskExecContext:
        """为某个步骤派生上下文（共享栅栏参数，记录 step_id 用于调用归属）。"""
        c = TaskExecContext(self.task_id, self.run_id, self.project_id, self.worker_id, self.cancel_generation,
                            self.lease_epoch, self.max_llm_requests, self.budget_limit_minor_amt, step_id)
        c.lost = self.lost
        return c

    async def _fence(self, s: AsyncSession) -> None:
        task = await s.get(Task, self.task_id)
        run = await s.get(TaskRun, self.run_id)
        if self.lost or run is None or run.lease_epoch != self.lease_epoch or run.worker_id != self.worker_id:
            raise LeaseLost()
        if task is None or task.cancel_generation != self.cancel_generation:
            status = task.task_status if task else "stopping"
            raise TaskInterrupted("pause" if status in ("pausing", "paused") else "stop")

    async def check(self) -> None:
        async with session_scope() as s:
            await self._fence(s)

    async def ensure_budget(self) -> None:
        async with session_scope() as s:
            t = await s.get(Task, self.task_id)
            if t is None:
                raise TaskInterrupted("stop")
            if t.llm_request_qty >= self.max_llm_requests:
                raise BudgetExhausted(f"模型请求次数已达上限 {self.max_llm_requests}")
            if self.budget_limit_minor_amt is not None and t.spent_minor_amt >= self.budget_limit_minor_amt:
                raise BudgetExhausted("费用已达预算上限")

    async def charge(self, requests: int, cost_minor_amt: int | None) -> None:
        # 记账不受栅栏限制：停止后到达的已发生费用仍须入账
        async with session_scope() as s:
            values: dict[str, Any] = {"llm_request_qty": Task.llm_request_qty + requests}
            if cost_minor_amt is None:
                values["cost_unknown_qty"] = Task.cost_unknown_qty + 1
            else:
                values["spent_minor_amt"] = Task.spent_minor_amt + cost_minor_amt
            await s.execute(update(Task).where(Task.task_id == self.task_id).values(**values))

    async def reusable_output(self, node_id: str) -> dict[str, Any] | None:
        async with session_scope() as s:
            row = (await s.execute(select(TaskStep).where(
                TaskStep.task_id == self.task_id, TaskStep.node_id == node_id,
                TaskStep.step_status == "succeeded").order_by(TaskStep.created_time.desc()).limit(1))).scalar()
            return row.output_json if row else None

    async def step(self, node_id: str, fn: Callable[[TaskExecContext], Awaitable[StepResult]], *,
                   node_kind: str = "agent", agent_role: str | None = None,
                   input_json: dict | None = None) -> dict[str, Any]:
        from ..core.tracelog import trace

        reused = await self.reusable_output(node_id)
        if reused is not None:
            trace("step", f"{node_id} 复用上次已完成的结果")
            return reused
        await self.check()
        step_id = new_id("step")
        t0 = time.monotonic()
        trace("step", f"{node_id} 开始", role=agent_role, kind=node_kind)

        def done(status: str, err: str | None = None) -> None:
            trace("step", f"{node_id} {status}（{time.monotonic() - t0:.1f}s）", error=err)

        try:
            async with session_scope() as s:
                attempt = (await s.execute(select(func.count()).select_from(TaskStep).where(
                    TaskStep.task_id == self.task_id, TaskStep.node_id == node_id,
                    TaskStep.cancel_generation == self.cancel_generation))).scalar_one() + 1
                s.add(TaskStep(step_id=step_id, task_id=self.task_id, run_id=self.run_id, node_id=node_id[:128],
                               node_kind=node_kind, agent_role=agent_role, step_status="running",
                               cancel_generation=self.cancel_generation, attempt_no=attempt,
                               lease_epoch=self.lease_epoch, input_json=input_json, started_time=utcnow()))
            result = await fn(self.for_step(step_id))
        except TaskInterrupted:
            done("被中断")
            await self._finish_step(step_id, "cancelled", error_code="interrupted")
            raise
        except asyncio.CancelledError:
            # 并发兄弟节点因停止被取消：收尾记录后继续传播取消
            done("已取消")
            await self._finish_step(step_id, "cancelled", error_code="cancelled")
            raise
        except LeaseLost:
            raise
        except BudgetExhausted as e:
            done("额度用尽", str(e))
            await self._finish_step(step_id, "failed", error_code="budget_exhausted", error_desc=str(e))
            raise
        except Exception as e:
            done("失败", f"{type(e).__name__}: {str(e)[:800]}")
            await self._finish_step(step_id, "failed", error_code=type(e).__name__, error_desc=str(e)[:2000])
            raise
        # 带栅栏提交：结果与持久化写入同事务
        try:
            async with session_scope() as s:
                await self._fence(s)
                if result.persist:
                    await result.persist(s)
                row = await s.get(TaskStep, step_id)
                row.step_status = "succeeded"
                row.output_json = result.output
                row.output_hash = sha256_json(result.output)
                row.finished_time = utcnow()
        except (TaskInterrupted, LeaseLost):
            done("结果作废（已停止/租约丢失）")
            await self._finish_step(step_id, "cancelled", error_code="late_result_quarantined")
            raise
        except asyncio.CancelledError:
            await self._finish_step(step_id, "cancelled", error_code="cancelled")
            raise
        done("完成")
        return result.output

    async def _finish_step(self, step_id: str, status: str, *, error_code: str | None = None,
                           error_desc: str | None = None) -> None:
        """收尾记录必须落库：即使当前协程正被取消，也等待这次短事务完成后再传播取消。"""
        inner = asyncio.ensure_future(self._finish_step_now(step_id, status, error_code, error_desc))
        try:
            await asyncio.shield(inner)
        except asyncio.CancelledError:
            await inner
            raise

    async def _finish_step_now(self, step_id: str, status: str, error_code: str | None,
                               error_desc: str | None) -> None:
        async with session_scope() as s:
            row = await s.get(TaskStep, step_id)
            if row and row.step_status == "running":
                row.step_status, row.error_code, row.error_desc = status, error_code, error_desc
                row.finished_time = utcnow()
