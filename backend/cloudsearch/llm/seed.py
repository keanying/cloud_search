"""把 config.yaml 的 llm 分区同步进数据库（启动时执行，幂等）。

- 供应方按名称、模型按（供应方, 模型名）、绑定按角色进行新增或更新；YAML 中列出的条目以 YAML 为准
- 管理后台中另行添加、但 YAML 未列出的条目保持不变（不会被删除）
- 单价在 YAML 中按“元/百万 token”填写，入库换算为分
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.base import ROLE_INFO
from ..core.config import ConfigError, load_config_file
from ..core.ids import new_id
from ..core.security import encrypt_secret, mask_secret
from ..db.models import AgentModelBinding, LlmModel, LlmProvider

log = logging.getLogger(__name__)


class ModelCfg(BaseModel, extra="forbid"):
    name: str
    display_name: str | None = None
    supports_tools: bool = True
    # 留空 = 不覆盖（保留运行中自动探测的结果）；思考模式模型可显式设为 false
    supports_forced_tool_choice: bool | None = None
    supports_json_schema: bool = False
    supports_json_object: bool = True
    supports_vision: bool = False
    context_window: int | None = None
    max_output: int | None = None
    input_price: float | None = Field(default=None, description="元/百万输入token")
    output_price: float | None = Field(default=None, description="元/百万输出token")
    currency: str = "CNY"
    enabled: bool = True


class ProviderCfg(BaseModel, extra="forbid"):
    name: str
    type: str = "openai_compatible"
    base_url: str
    api_key: str | None = None
    enabled: bool = True
    models: list[ModelCfg] = []


class BindingCfg(BaseModel, extra="forbid"):
    model: str = Field(description="供应方名称/模型名，例如 DeepSeek/deepseek-chat")
    fallbacks: list[str] = []
    temperature: float | None = None
    max_tokens: int | None = None


class LlmCfg(BaseModel, extra="forbid"):
    providers: list[ProviderCfg] = []
    bindings: dict[str, BindingCfg] = {}


def _fen(yuan: float | None) -> int | None:
    return None if yuan is None else round(yuan * 100)


def load_llm_config() -> LlmCfg | None:
    raw = load_config_file().get("llm")
    if not raw:
        return None
    try:
        return LlmCfg.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(f"config.yaml 的 llm 分区有误：{e}") from e


SYNC_HASH_KEY = "_llm_config_hash"


async def sync_llm_config(s: AsyncSession, *, force: bool = False) -> dict[str, int]:
    """把 config.yaml 的 llm 分区同步进数据库。

    只在该分区内容变化后（或首次）同步：之后在管理后台做的修改不会在每次重启时被配置文件覆盖；
    修改 config.yaml 的 llm 分区后重启，则以配置文件为准重新同步。"""
    import hashlib
    import json

    from ..db.models import SystemSetting

    cfg = load_llm_config()
    if cfg is None:
        return {}
    digest = hashlib.sha256(json.dumps(cfg.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    mark = await s.get(SystemSetting, SYNC_HASH_KEY)
    if not force and mark is not None and mark.setting_value == digest:
        return {"skipped": 1}
    if mark is None:
        s.add(SystemSetting(setting_key=SYNC_HASH_KEY, setting_value=digest))
    else:
        mark.setting_value = digest
    stats = {"providers": 0, "models": 0, "bindings": 0}
    ref_to_id: dict[str, str] = {}
    for pc in cfg.providers:
        p = (await s.execute(select(LlmProvider).where(LlmProvider.provider_name == pc.name))).scalar()
        if p is None:
            p = LlmProvider(provider_id=new_id("llmp"), provider_name=pc.name, provider_type=pc.type,
                            base_url=pc.base_url)
            s.add(p)
        p.provider_type, p.base_url, p.enabled = pc.type, pc.base_url.rstrip("/"), pc.enabled
        if pc.api_key and not pc.api_key.startswith("<"):
            p.api_key_cipher, p.api_key_mask = encrypt_secret(pc.api_key), mask_secret(pc.api_key)
        await s.flush()
        stats["providers"] += 1
        for mc in pc.models:
            m = (await s.execute(select(LlmModel).where(LlmModel.provider_id == p.provider_id,
                                                        LlmModel.model_name == mc.name))).scalar()
            if m is None:
                m = LlmModel(model_profile_id=new_id("llmm"), provider_id=p.provider_id, model_name=mc.name)
                s.add(m)
            m.display_name = mc.display_name
            m.supports_tools, m.supports_json_schema = mc.supports_tools, mc.supports_json_schema
            if mc.supports_forced_tool_choice is not None:
                m.supports_forced_tool_choice = mc.supports_forced_tool_choice
            m.supports_json_object, m.supports_vision = mc.supports_json_object, mc.supports_vision
            m.context_window_qty, m.max_output_qty = mc.context_window, mc.max_output
            m.input_price_minor_amt, m.output_price_minor_amt = _fen(mc.input_price), _fen(mc.output_price)
            m.currency_code, m.enabled = mc.currency, mc.enabled
            await s.flush()
            ref_to_id[f"{pc.name}/{mc.name}"] = m.model_profile_id
            stats["models"] += 1

    async def resolve(ref: str) -> str:
        if ref in ref_to_id:
            return ref_to_id[ref]
        prov, _, model = ref.partition("/")
        row = (await s.execute(select(LlmModel.model_profile_id).join(
            LlmProvider, LlmProvider.provider_id == LlmModel.provider_id).where(
            LlmProvider.provider_name == prov, LlmModel.model_name == model))).scalar()
        if row is None:
            raise ConfigError(f"llm.bindings 引用了不存在的模型：{ref}（格式：供应方名称/模型名）")
        return row

    for role, bc in cfg.bindings.items():
        if role not in ROLE_INFO:
            raise ConfigError(f"llm.bindings 中未知角色：{role}（可选：{', '.join(ROLE_INFO)}）")
        b = await s.get(AgentModelBinding, role)
        primary = await resolve(bc.model)
        if b is None:
            b = AgentModelBinding(agent_role=role, model_profile_id=primary)
            s.add(b)
        b.model_profile_id = primary
        b.fallback_profile_ids = [x for x in [await resolve(r) for r in bc.fallbacks] if x != primary]
        b.temperature, b.max_tokens = bc.temperature, bc.max_tokens
        stats["bindings"] += 1
    log.info("synced llm config from config.yaml: %s", stats)
    return stats
