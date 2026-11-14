from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic_ai import Agent, UsageLimits
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...agents.base import ROLE_INFO
from ...core.ids import new_id
from ...core.security import encrypt_secret, mask_secret
from ...db.base import get_session, session_scope
from ...db.models import AgentModelBinding, LlmModel, LlmProvider
from ...llm.presets import PROVIDER_PRESETS
from ...llm.registry import build_model
from ..deps import CurrentUser, admin_user
from ..schemas import (
    AgentBindingIn,
    AgentBindingOut,
    ModelIn,
    ModelOut,
    ModelPatch,
    ModelTestOut,
    ProviderIn,
    ProviderOut,
    ProviderPatch,
    ProviderPreset,
)

router = APIRouter(prefix="/admin/llm", tags=["admin-llm"])


def _p_out(p: LlmProvider) -> ProviderOut:
    return ProviderOut(provider_id=p.provider_id, provider_name=p.provider_name, provider_type=p.provider_type,
                       base_url=p.base_url, has_api_key=bool(p.api_key_cipher), api_key_mask=p.api_key_mask,
                       enabled=p.enabled)


def _m_out(m: LlmModel, provider_name: str | None) -> ModelOut:
    return ModelOut(model_profile_id=m.model_profile_id, provider_id=m.provider_id, provider_name=provider_name,
                    model_name=m.model_name, display_name=m.display_name, supports_tools=m.supports_tools,
                    supports_forced_tool_choice=m.supports_forced_tool_choice,
                    supports_json_schema=m.supports_json_schema, supports_json_object=m.supports_json_object,
                    supports_vision=m.supports_vision, context_window_qty=m.context_window_qty,
                    max_output_qty=m.max_output_qty, input_price_minor_amt=m.input_price_minor_amt,
                    output_price_minor_amt=m.output_price_minor_amt, currency_code=m.currency_code, enabled=m.enabled)


@router.get("/provider-presets", response_model=list[ProviderPreset])
async def presets(_: CurrentUser = Depends(admin_user)):
    return PROVIDER_PRESETS


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers(_: CurrentUser = Depends(admin_user), s: AsyncSession = Depends(get_session)):
    return [_p_out(p) for p in (await s.execute(select(LlmProvider).order_by(LlmProvider.created_time))).scalars()]


@router.post("/providers", response_model=ProviderOut, status_code=201)
async def create_provider(body: ProviderIn, _: CurrentUser = Depends(admin_user),
                          s: AsyncSession = Depends(get_session)):
    p = LlmProvider(provider_id=new_id("llmp"), provider_name=body.provider_name, provider_type=body.provider_type,
                    base_url=body.base_url.rstrip("/"), enabled=body.enabled)
    if body.api_key:
        p.api_key_cipher, p.api_key_mask = encrypt_secret(body.api_key), mask_secret(body.api_key)
    s.add(p)
    await s.commit()
    return _p_out(p)


@router.patch("/providers/{provider_id}", response_model=ProviderOut)
async def patch_provider(provider_id: str, body: ProviderPatch, _: CurrentUser = Depends(admin_user),
                         s: AsyncSession = Depends(get_session)):
    p = await s.get(LlmProvider, provider_id)
    if p is None:
        raise HTTPException(404, "供应方不存在")
    if body.provider_name is not None:
        p.provider_name = body.provider_name
    if body.base_url is not None:
        p.base_url = body.base_url.rstrip("/")
    if body.enabled is not None:
        p.enabled = body.enabled
    if body.api_key:
        p.api_key_cipher, p.api_key_mask = encrypt_secret(body.api_key), mask_secret(body.api_key)
    await s.commit()
    return _p_out(p)


@router.delete("/providers/{provider_id}", status_code=204)
async def delete_provider(provider_id: str, _: CurrentUser = Depends(admin_user),
                          s: AsyncSession = Depends(get_session)):
    p = await s.get(LlmProvider, provider_id)
    if p is None:
        raise HTTPException(404, "供应方不存在")
    if (await s.execute(select(LlmModel).where(LlmModel.provider_id == provider_id).limit(1))).scalar():
        raise HTTPException(409, "请先删除该供应方下的模型")
    await s.delete(p)
    await s.commit()
    return Response(status_code=204)


@router.get("/models", response_model=list[ModelOut])
async def list_models(_: CurrentUser = Depends(admin_user), s: AsyncSession = Depends(get_session)):
    rows = (await s.execute(select(LlmModel, LlmProvider.provider_name).join(
        LlmProvider, LlmProvider.provider_id == LlmModel.provider_id).order_by(LlmModel.created_time))).all()
    return [_m_out(m, name) for m, name in rows]


@router.post("/models", response_model=ModelOut, status_code=201)
async def create_model(body: ModelIn, _: CurrentUser = Depends(admin_user), s: AsyncSession = Depends(get_session)):
    p = await s.get(LlmProvider, body.provider_id)
    if p is None:
        raise HTTPException(422, "供应方不存在")
    if (await s.execute(select(LlmModel).where(LlmModel.provider_id == body.provider_id,
                                               LlmModel.model_name == body.model_name))).scalar():
        raise HTTPException(409, "该供应方下已存在同名模型")
    m = LlmModel(model_profile_id=new_id("llmm"), **body.model_dump())
    s.add(m)
    await s.commit()
    return _m_out(m, p.provider_name)


@router.patch("/models/{model_profile_id}", response_model=ModelOut)
async def patch_model(model_profile_id: str, body: ModelPatch, _: CurrentUser = Depends(admin_user),
                      s: AsyncSession = Depends(get_session)):
    m = await s.get(LlmModel, model_profile_id)
    if m is None:
        raise HTTPException(404, "模型不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    p = await s.get(LlmProvider, m.provider_id)
    await s.commit()
    return _m_out(m, p.provider_name if p else None)


@router.delete("/models/{model_profile_id}", status_code=204)
async def delete_model(model_profile_id: str, _: CurrentUser = Depends(admin_user),
                       s: AsyncSession = Depends(get_session)):
    m = await s.get(LlmModel, model_profile_id)
    if m is None:
        raise HTTPException(404, "模型不存在")
    bindings = (await s.execute(select(AgentModelBinding))).scalars().all()
    if any(b.model_profile_id == model_profile_id or model_profile_id in (b.fallback_profile_ids or [])
           for b in bindings):
        raise HTTPException(409, "该模型仍被智能体绑定使用，请先修改绑定")
    await s.delete(m)
    await s.commit()
    return Response(status_code=204)


@router.post("/models/{model_profile_id}/test", response_model=ModelTestOut)
async def test_model(model_profile_id: str, _: CurrentUser = Depends(admin_user),
                     s: AsyncSession = Depends(get_session)):
    """连通性测试 + 结构化输出测试（与智能体实际调用方式一致；不支持时自动调整能力配置并重试）。"""
    from pydantic import BaseModel as _BM

    from ...llm.adapt import apply_adaptations, classify

    m = await s.get(LlmModel, model_profile_id)
    p = await s.get(LlmProvider, m.provider_id) if m else None
    if m is None or p is None:
        raise HTTPException(404, "模型不存在")
    await s.commit()
    started = time.monotonic()
    try:
        agent = Agent(build_model(m, p), instructions="你是连通性测试助手，只回复“连接正常”。")
        r = await agent.run("测试", usage_limits=UsageLimits(request_limit=1), model_settings={"timeout": 30,
                                                                                           "max_tokens": 64})
        reply = str(r.output)[:200]
    except Exception as e:  # noqa: BLE001
        return ModelTestOut(ok=False, latency_ms=int((time.monotonic() - started) * 1000),
                            error=f"{type(e).__name__}: {str(e)[:300]}")
    latency = int((time.monotonic() - started) * 1000)

    class Probe(_BM):
        status: str
        number: int

    adaptations: list[str] = []
    structured_ok, error = False, None
    for _attempt in range(3):
        async with session_scope() as db:
            m2 = await db.get(LlmModel, model_profile_id)
            p2 = await db.get(LlmProvider, m2.provider_id)
            model = build_model(m2, p2)
        try:
            out = await Agent(model, output_type=Probe, retries=2,
                              instructions="按要求输出结构化结果：status 填 ok，number 填 42。").run(
                "开始", usage_limits=UsageLimits(request_limit=4), model_settings={"timeout": 60})
            structured_ok = out.output.number == 42
            error = None if structured_ok else "结构化输出内容不符合预期"
            break
        except Exception as e:  # noqa: BLE001
            actions = classify(e)
            changed = await apply_adaptations(actions, {m.model_name: model_profile_id}) if actions else []
            if not changed:
                error = f"结构化输出失败：{type(e).__name__}: {str(e)[:300]}"
                break
            adaptations += changed
    return ModelTestOut(ok=structured_ok, latency_ms=latency, reply=reply, structured_ok=structured_ok,
                        error=error, adaptations=adaptations)


@router.get("/agent-bindings", response_model=list[AgentBindingOut])
async def list_bindings(_: CurrentUser = Depends(admin_user), s: AsyncSession = Depends(get_session)):
    rows = {b.agent_role: b for b in (await s.execute(select(AgentModelBinding))).scalars()}
    out = []
    for role, (label, desc) in ROLE_INFO.items():
        b = rows.get(role)
        out.append(AgentBindingOut(agent_role=role, role_label=label, description=desc,
                                   model_profile_id=b.model_profile_id if b else None,
                                   fallback_profile_ids=b.fallback_profile_ids if b else [],
                                   temperature=b.temperature if b else None, max_tokens=b.max_tokens if b else None))
    return out


@router.put("/agent-bindings/{role}", response_model=AgentBindingOut)
async def put_binding(role: str, body: AgentBindingIn, _: CurrentUser = Depends(admin_user),
                      s: AsyncSession = Depends(get_session)):
    if role not in ROLE_INFO:
        raise HTTPException(404, "未知角色")
    for pid in [body.model_profile_id, *body.fallback_profile_ids]:
        if await s.get(LlmModel, pid) is None:
            raise HTTPException(422, f"模型不存在: {pid}")
    b = await s.get(AgentModelBinding, role)
    if b is None:
        b = AgentModelBinding(agent_role=role, model_profile_id=body.model_profile_id)
        s.add(b)
    b.model_profile_id = body.model_profile_id
    b.fallback_profile_ids = [x for x in body.fallback_profile_ids if x != body.model_profile_id]
    b.temperature, b.max_tokens = body.temperature, body.max_tokens
    await s.commit()
    label, desc = ROLE_INFO[role]
    return AgentBindingOut(agent_role=role, role_label=label, description=desc, model_profile_id=b.model_profile_id,
                           fallback_profile_ids=b.fallback_profile_ids, temperature=b.temperature,
                           max_tokens=b.max_tokens)


@router.delete("/agent-bindings/{role}", status_code=204)
async def delete_binding(role: str, _: CurrentUser = Depends(admin_user), s: AsyncSession = Depends(get_session)):
    """取消某个角色的单独绑定，改用默认模型（默认模型本身不能取消）。"""
    if role not in ROLE_INFO:
        raise HTTPException(404, "未知角色")
    if role == "default":
        raise HTTPException(400, "默认模型不能取消，请改选其他模型")
    b = await s.get(AgentModelBinding, role)
    if b is not None:
        await s.delete(b)
        await s.commit()
    return Response(status_code=204)
