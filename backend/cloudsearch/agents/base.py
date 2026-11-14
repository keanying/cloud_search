"""智能体公共层：角色定义、AgentSpec、统一调用入口（模型解析、栅栏检查、预算、用量与费用记录）。

每个智能体是一个独立子包（agents/<role>/），只声明：输入/输出类型、指令、可用工具。
调度、并发、停止、预算由 orchestrator 负责；智能体不能自行领取租约、改预算或宣布任务完成。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import asyncio
import json
import logging
import time

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Generic, Protocol, TypeVar

from pydantic_ai import Agent, UsageLimits
from pydantic_ai.messages import ModelResponse

from ..core.ids import new_id, utcnow
from ..db.base import session_scope
from ..db.models import AgentRun
from ..llm.registry import resolve_model


class AgentRole(StrEnum):
    requirement_compiler = "requirement_compiler"
    coordinator = "coordinator"
    search_planner = "search_planner"
    browser_researcher = "browser_researcher"
    extractor = "extractor"
    verifier = "verifier"
    analyst = "analyst"
    report_writer = "report_writer"


ROLE_INFO: dict[str, tuple[str, str]] = {
    "default": ("默认模型", "未单独绑定的角色使用此模型"),
    "requirement_compiler": ("需求编译", "识别意图、澄清问题、生成任务规格（TaskSpec）"),
    "coordinator": ("协调", "评估覆盖度并决定是否补查（调度本身由程序执行）"),
    "search_planner": ("搜索规划", "把问题拆成搜索词矩阵"),
    "browser_researcher": ("浏览研究", "需要翻页/展开等交互时决定下一步浏览动作"),
    "extractor": ("信息抽取", "从实际读取的正文中抽取事实/字段及原文摘录"),
    "verifier": ("核验", "跨来源核对冲突与支持度"),
    "analyst": ("分析", "制定计算方案（由程序确定性执行）"),
    "report_writer": ("报告写作", "撰写带引用的回答/报告"),
}

log = logging.getLogger(__name__)

O = TypeVar("O")


class ExecContext(Protocol):
    """由 orchestrator 提供的执行上下文。"""

    task_id: str
    step_id: str | None

    async def check(self) -> None:
        """栅栏：任务已停止/暂停或租约丢失时抛异常，阻止新动作与有价请求。"""

    async def ensure_budget(self) -> None:
        """预算/请求额度不足时抛异常。"""

    async def charge(self, requests: int, cost_minor_amt: int | None) -> None:
        """记账（cost 为 None 表示单价未知，不记 0）。"""


@dataclass
class AgentSpec(Generic[O]):
    role: AgentRole
    output_type: Any
    instructions: str
    tools: list = field(default_factory=list)
    deps_type: Any = type(None)
    retries: int = 2
    request_limit: int = 6


MAX_ADAPT_ATTEMPTS = 2  # 能力自适应最多降级重试次数


async def run_agent(spec: AgentSpec[O], prompt: str, *, deps: Any = None, ctx: ExecContext | None = None,
                    conversation_id: str | None = None,
                    on_partial: Callable[[O], Awaitable[None]] | None = None) -> O:
    """调用一个智能体并返回经校验的结构化输出。

    若供应方因“不支持强制工具调用 / 思考模式”等返回 400，会自动降级输出方式、写回模型配置并重试。
    """
    from ..llm.adapt import apply_adaptations, classify

    for attempt in range(MAX_ADAPT_ATTEMPTS + 1):
        async with session_scope() as s:
            resolved = await resolve_model(s, spec.role.value)
        try:
            return await _run_once(spec, prompt, resolved, deps=deps, ctx=ctx, conversation_id=conversation_id,
                                   on_partial=on_partial)
        except Exception as e:
            actions = classify(e)
            if not actions or not resolved.pricing or attempt == MAX_ADAPT_ATTEMPTS:
                raise
            ids = {name: p.model_profile_id for name, p in resolved.pricing.items()}
            if not await apply_adaptations(actions, ids):
                raise
    raise AssertionError("unreachable")


def _partial_output(output_type: Any, raw: str) -> Any | None:
    """把流式中途的（不完整）JSON 解析成输出模型；缺的字段用默认值。解析不了返回 None。"""
    from pydantic_core import from_json

    try:
        data = from_json(raw, allow_partial="trailing-strings")
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return output_type.model_validate(data)
    except Exception:  # noqa: BLE001 —— 必填字段还没生成：用默认值占位，只用于展示
        fields = getattr(output_type, "model_fields", {})
        return output_type.model_construct(**{k: v for k, v in data.items() if k in fields})


async def _invoke(agent: Agent, prompt: str, deps: Any, limits: UsageLimits, output_type: Any,
                  on_partial: Callable[[Any], Awaitable[None]] | None):
    """on_partial 不为空时：普通 run()（保留输出校验与自动重试）+ 事件流，边生成边回调部分结果。
    模型/适配器不支持流式时退回普通调用。"""
    if on_partial is None:
        return await agent.run(prompt, deps=deps, usage_limits=limits)
    from pydantic_ai.messages import PartDeltaEvent, PartStartEvent, TextPart, TextPartDelta, ToolCallPart, \
        ToolCallPartDelta

    loop = asyncio.get_running_loop()

    async def handler(_ctx, events) -> None:
        bufs: dict[int, str] = {}
        last = 0.0
        async for ev in events:
            idx = None
            if isinstance(ev, PartStartEvent):
                idx = ev.index
                part = ev.part
                if isinstance(part, ToolCallPart):
                    bufs[idx] = part.args if isinstance(part.args, str) else json.dumps(part.args or {})
                elif isinstance(part, TextPart):
                    bufs[idx] = part.content
            elif isinstance(ev, PartDeltaEvent):
                idx = ev.index
                d = ev.delta
                if isinstance(d, ToolCallPartDelta) and isinstance(d.args_delta, str):
                    bufs[idx] = bufs.get(idx, "") + d.args_delta
                elif isinstance(d, ToolCallPartDelta) and isinstance(d.args_delta, dict):
                    bufs[idx] = json.dumps(d.args_delta)
                elif isinstance(d, TextPartDelta):
                    bufs[idx] = bufs.get(idx, "") + d.content_delta
            if idx is None or loop.time() - last < 0.3:
                continue
            raw = bufs.get(idx, "")
            brace = raw.find("{")
            if brace < 0:
                continue
            partial = _partial_output(output_type, raw[brace:])
            if partial is not None:
                last = loop.time()
                try:
                    await on_partial(partial)
                except Exception:  # noqa: BLE001 —— 展示失败不影响撰写
                    log.debug("on_partial failed", exc_info=True)

    try:
        return await agent.run(prompt, deps=deps, usage_limits=limits, event_stream_handler=handler)
    except AssertionError as e:
        if "stream" not in str(e):
            raise
        return await agent.run(prompt, deps=deps, usage_limits=limits)


async def _run_once(spec: AgentSpec[O], prompt: str, resolved, *, deps: Any, ctx: ExecContext | None,
                    conversation_id: str | None, on_partial: Callable[[O], Awaitable[None]] | None = None) -> O:
    if ctx is not None:
        await ctx.check()
        await ctx.ensure_budget()

    settings: dict[str, Any] = {"timeout": 120}
    if resolved.temperature is not None:
        settings["temperature"] = resolved.temperature
    if resolved.max_tokens is not None:
        settings["max_tokens"] = resolved.max_tokens

    agent = Agent(resolved.model, output_type=spec.output_type, instructions=spec.instructions,
                  tools=spec.tools, deps_type=spec.deps_type, retries=spec.retries,
                  model_settings=settings, name=spec.role.value)
    started = utcnow()
    run = AgentRun(agent_run_id=new_id("arun"), task_id=ctx.task_id if ctx else None,
                   step_id=ctx.step_id if ctx else None, conversation_id=conversation_id,
                   agent_role=spec.role.value, model_profile_id=resolved.primary_profile_id, started_time=started)
    from ..core.config import get_settings
    from ..core.tracelog import trace

    t0 = time.monotonic()
    want_prompt = get_settings().logs_include_prompts
    try:
        result = await _invoke(agent, prompt, deps, UsageLimits(request_limit=spec.request_limit), spec.output_type,
                               on_partial)
    except Exception as e:
        trace("llm", f"{spec.role.value} 调用失败（{time.monotonic() - t0:.1f}s）：{type(e).__name__}: {str(e)[:500]}",
              prompt_chars=len(prompt), status_code=getattr(e, "status_code", None),
              prompt=prompt if want_prompt else None)
        rejected = getattr(e, "status_code", None) in (400, 422)
        run.run_status = "failed"
        run.error_desc = f"{type(e).__name__}: {e}"[:2000]
        run.finished_time = utcnow()
        # 参数被拒（400）的请求不计费；其他失败可能已计费，记为未知待对账
        run.cost_status = "not_billed" if rejected else "unknown"
        run.cost_minor_amt = 0 if rejected else None
        async with session_scope() as s:
            s.add(run)
        if ctx is not None:
            await ctx.charge(1, 0 if rejected else None)
        raise

    # 按每次实际响应的模型计价（备用模型可能接管）
    total_cost: int | None = 0
    in_tok = out_tok = reqs = 0
    model_name = provider_name = currency = None
    for msg in result.all_messages():
        if not isinstance(msg, ModelResponse):
            continue
        reqs += 1
        u = msg.usage
        in_tok += u.input_tokens or 0
        out_tok += u.output_tokens or 0
        model_name = msg.model_name or model_name
        price = resolved.pricing.get(msg.model_name or "")
        c = price.cost(u.input_tokens or 0, u.output_tokens or 0) if price else None
        if price:
            provider_name, currency = price.provider_name, price.currency_code
        total_cost = None if (c is None or total_cost is None) else total_cost + c
    if not resolved.pricing:  # 测试注入模型：不计费
        total_cost = 0
    run.request_qty, run.input_token_qty, run.output_token_qty = reqs, in_tok, out_tok
    run.model_name, run.provider_name, run.currency_code = model_name, provider_name, currency
    run.cost_minor_amt = total_cost
    run.cost_status = "confirmed" if total_cost is not None else "unknown"
    run.finished_time = utcnow()
    trace("llm", f"{spec.role.value} · {provider_name or ''} {model_name or ''}（{time.monotonic() - t0:.1f}s）",
          requests=reqs, input_tokens=in_tok, output_tokens=out_tok, prompt_chars=len(prompt),
          prompt=prompt if want_prompt else None,
          output=(result.output.model_dump_json()[:4000] if hasattr(result.output, "model_dump_json")
                  else str(result.output)[:4000]) if want_prompt else None)
    async with session_scope() as s:
        s.add(run)
    if ctx is not None:
        await ctx.charge(reqs, total_cost)
    return result.output
