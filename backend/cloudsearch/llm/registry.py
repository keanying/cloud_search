"""按智能体角色解析模型：角色绑定 → 主模型 + 备用模型链；能力矩阵 → pydantic-ai ModelProfile。

- 所有供应方通过 OpenAI 兼容接口接入（OpenAIProvider(base_url, api_key)）。
- 结构化输出方式按能力自动选择：支持工具调用→tool；仅支持 JSON Schema→native；否则→prompted。
- 测试/离线可用 set_model_override() 注入 TestModel/FunctionModel，不触网、不计费。
"""

from __future__ import annotations

import asyncio

import math
from collections.abc import Callable
from dataclasses import dataclass

from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import decrypt_secret
from ..db.models import AgentModelBinding, LlmModel, LlmProvider

DEFAULT_ROLE = "default"


class LlmNotConfigured(Exception):
    """角色未绑定可用模型（且无 default 绑定）。"""


@dataclass
class ModelPricing:
    model_profile_id: str
    provider_name: str
    model_name: str
    input_price_minor_amt: int | None
    output_price_minor_amt: int | None
    currency_code: str

    def cost(self, input_tokens: int, output_tokens: int) -> int | None:
        """按每百万 token 单价（分）计算，向上取整；任一单价未知返回 None（不记 0）。"""
        if self.input_price_minor_amt is None or self.output_price_minor_amt is None:
            return None
        return math.ceil((input_tokens * self.input_price_minor_amt + output_tokens * self.output_price_minor_amt) / 1e6)


@dataclass
class ResolvedModel:
    model: Model
    pricing: dict[str, ModelPricing]  # key: model_name
    primary_profile_id: str | None
    temperature: float | None
    max_tokens: int | None


_overrides: dict[str, Model | Callable[[], Model]] = {}


def set_model_override(role: str, model: Model | Callable[[], Model] | None) -> None:
    """测试用：为某角色（或 '*'）注入模型。传 None 取消。"""
    if model is None:
        _overrides.pop(role, None)
    else:
        _overrides[role] = model


def clear_model_overrides() -> None:
    _overrides.clear()


def build_profile(m: LlmModel) -> dict:
    if m.supports_tools:
        mode = "tool"
    elif m.supports_json_schema:
        mode = "native"
    else:
        mode = "prompted"
    profile = {
        "supports_tools": m.supports_tools,
        "supports_json_schema_output": m.supports_json_schema,
        "supports_json_object_output": m.supports_json_object,
        "supports_image_input": m.supports_vision,
        "default_structured_output_mode": mode,
    }
    # 只在明确不支持时覆盖：思考模式常不接受 tool_choice=required，关闭后输出工具以 tool_choice=auto 调用。
    # 支持时不写入，以保留专用供应方（如 DeepSeek）按模型/是否思考的更精确判断。
    if not m.supports_forced_tool_choice:
        profile["supports_forced_tool_choice"] = False
    return profile


def build_provider(p: LlmProvider):
    """按供应方类型选用 pydantic-ai 专用适配器（处理思考模式、reasoning_content 回传等差异），
    其余使用通用 OpenAI 兼容适配器。始终使用管理员配置的 base_url。"""
    from openai import AsyncOpenAI

    api_key = decrypt_secret(p.api_key_cipher) if p.api_key_cipher else "EMPTY"
    client = AsyncOpenAI(base_url=p.base_url, api_key=api_key)
    try:
        if p.provider_type == "deepseek":
            from pydantic_ai.providers.deepseek import DeepSeekProvider

            return DeepSeekProvider(openai_client=client)
        if p.provider_type == "moonshot":
            from pydantic_ai.providers.moonshotai import MoonshotAIProvider

            return MoonshotAIProvider(openai_client=client)
        if p.provider_type == "dashscope":
            from pydantic_ai.providers.alibaba import AlibabaProvider

            return AlibabaProvider(openai_client=client)
        if p.provider_type == "zhipu":
            from pydantic_ai.providers.zai import ZaiProvider

            return ZaiProvider(openai_client=client)
    except Exception:  # noqa: BLE001  专用适配器不可用时退回通用适配器
        pass
    return OpenAIProvider(openai_client=client)


def build_model(m: LlmModel, p: LlmProvider) -> OpenAIChatModel:
    return OpenAIChatModel(m.model_name, provider=build_provider(p), profile=build_profile(m))


async def _load_profile(session: AsyncSession, profile_id: str) -> tuple[LlmModel, LlmProvider] | None:
    m = await session.get(LlmModel, profile_id)
    if m is None or not m.enabled:
        return None
    p = await session.get(LlmProvider, m.provider_id)
    if p is None or not p.enabled:
        return None
    return m, p


async def resolve_model(session: AsyncSession, role: str) -> ResolvedModel:
    ov = _overrides.get(role) or _overrides.get("*")
    if ov is not None:
        model = ov() if callable(ov) and not isinstance(ov, Model) else ov
        return ResolvedModel(model=model, pricing={}, primary_profile_id=None, temperature=None, max_tokens=None)

    binding = await session.get(AgentModelBinding, role) or await session.get(AgentModelBinding, DEFAULT_ROLE)
    if binding is None:
        # 无任何绑定：若只配置了一个可用模型则直接使用，降低首次配置门槛
        rows = (await session.execute(select(LlmModel).where(LlmModel.enabled.is_(True)))).scalars().all()
        if len(rows) != 1:
            raise LlmNotConfigured(f"智能体角色「{role}」未绑定模型，请在 管理后台→大模型 中配置")
        profile_ids = [rows[0].model_profile_id]
        temperature = max_tokens = None
    else:
        profile_ids = [binding.model_profile_id, *(binding.fallback_profile_ids or [])]
        temperature, max_tokens = binding.temperature, binding.max_tokens

    models: list[Model] = []
    pricing: dict[str, ModelPricing] = {}
    primary: str | None = None
    from ..core import privacy

    blocked: list[str] = []
    for pid in profile_ids:
        loaded = await _load_profile(session, pid)
        if loaded is None:
            continue
        m, p = loaded
        if privacy.enabled() and not await asyncio.to_thread(privacy.url_internal, p.base_url):
            blocked.append(f"{p.provider_name}（{p.base_url}）")
            continue
        primary = primary or m.model_profile_id
        models.append(build_model(m, p))
        pricing[m.model_name] = ModelPricing(m.model_profile_id, p.provider_name, m.model_name,
                                             m.input_price_minor_amt, m.output_price_minor_amt, m.currency_code)
    if not models:
        if blocked:
            raise LlmNotConfigured(f"已开启数据不出域，智能体角色「{role}」绑定的模型不在本机/内网："
                                   f"{'、'.join(blocked)}。请绑定本地模型（如 Ollama、vLLM），"
                                   "或把内部网关域名加入 config.yaml 的 privacy.allowed_hosts")
        raise LlmNotConfigured(f"智能体角色「{role}」绑定的模型不可用（已停用或供应方被禁用）")
    model: Model = models[0] if len(models) == 1 else FallbackModel(models[0], *models[1:])
    return ResolvedModel(model=model, pricing=pricing, primary_profile_id=primary,
                         temperature=temperature, max_tokens=max_tokens)
