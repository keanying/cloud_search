"""模型能力自适应：根据供应方返回的 400 错误自动降级结构化输出方式，并把探测到的能力写回模型配置。

降级顺序：
  1. 强制工具调用（tool_choice=required）被拒，常见于思考模式（DeepSeek / Kimi / 豆包 / 千问的思考模型）
     → supports_forced_tool_choice=False：改为 tool_choice=auto，由模型自行调用输出工具
  2. 仍报不支持工具/函数调用 → supports_tools=False：改为提示词约束 JSON（prompted）
写回数据库后，下次调用直接使用正确方式；管理后台可看到并手动修改。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator

from sqlalchemy import select

from ..db.base import session_scope
from ..db.models import LlmModel

log = logging.getLogger(__name__)

_FORCED_RE = re.compile(r"tool_choice|forced tool|thinking mode|reasoning mode|思考模式", re.I)
_TOOLS_RE = re.compile(r"(not|n't|unsupported).{0,40}(tools?|function[ _]?call(ing)?)|"
                       r"(tools?|function[ _]?call(ing)?).{0,40}(not supported|unsupported)|不支持.{0,10}(工具|函数)", re.I)

ACTION_NO_FORCED = "no_forced_tool_choice"
ACTION_NO_TOOLS = "no_tools"


def _iter_errors(e: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    stack = [e]
    while stack:
        x = stack.pop()
        if id(x) in seen:
            continue
        seen.add(id(x))
        yield x
        if isinstance(x, BaseExceptionGroup):
            stack.extend(x.exceptions)
        if x.__cause__ is not None:
            stack.append(x.__cause__)


def classify(e: BaseException) -> dict[str, str]:
    """返回 {模型名: 降级动作}。只识别 400 类“请求参数不被支持”的错误。"""
    out: dict[str, str] = {}
    for err in _iter_errors(e):
        status = getattr(err, "status_code", None)
        model_name = getattr(err, "model_name", None)
        if status not in (400, 422) or not model_name:
            continue
        text = f"{err} {getattr(err, 'body', '')}"
        if _FORCED_RE.search(text):
            out[model_name] = ACTION_NO_FORCED
        elif _TOOLS_RE.search(text):
            out[model_name] = ACTION_NO_TOOLS
    return out


async def apply_adaptations(actions: dict[str, str], profile_ids: dict[str, str]) -> list[str]:
    """把降级写回模型配置；返回实际发生变化的说明（为空表示无可降级项）。"""
    changed: list[str] = []
    async with session_scope() as s:
        for model_name, action in actions.items():
            pid = profile_ids.get(model_name)
            if not pid:
                continue
            m = (await s.execute(select(LlmModel).where(LlmModel.model_profile_id == pid))).scalar()
            if m is None:
                continue
            if action == ACTION_NO_FORCED and m.supports_forced_tool_choice:
                m.supports_forced_tool_choice = False
                changed.append(f"{model_name}: 不支持强制工具调用（思考模式），已改为自动工具调用")
            elif action == ACTION_NO_FORCED and m.supports_tools:
                # 已经是非强制仍报 tool_choice 相关错误 → 进一步改为提示词约束输出
                m.supports_tools = False
                changed.append(f"{model_name}: 工具调用不可用，已改为提示词约束 JSON 输出")
            elif action == ACTION_NO_TOOLS and m.supports_tools:
                m.supports_tools = False
                changed.append(f"{model_name}: 不支持工具调用，已改为提示词约束 JSON 输出")
    for c in changed:
        log.warning("模型能力自适应：%s", c)
    return changed
