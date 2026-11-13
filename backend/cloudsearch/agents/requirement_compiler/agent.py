from __future__ import annotations

from datetime import date

from ...contracts import ReportSpec, TaskSpec
from ..base import AgentRole, AgentSpec, run_agent
from .prompts import INSTRUCTIONS, build_prompt
from .schemas import IntentDecision

SPEC: AgentSpec[IntentDecision] = AgentSpec(
    role=AgentRole.requirement_compiler,
    output_type=IntentDecision,
    instructions=INSTRUCTIONS,
    request_limit=4,
)


def normalize_decision(d: IntentDecision, mode_selection: str) -> IntentDecision:
    """确定性预检：补齐/修正模型输出，保证 TaskSpec 自洽。"""
    if d.kind == "task" and d.task_spec is None:
        # 模型声明要执行却没有规格：降级为澄清，不猜测开跑
        d.kind = "clarify"
        if not d.questions:
            d.questions = ["能否再具体描述一下你想查找或采集的内容？"]
        return d
    if d.kind != "task" or d.task_spec is None:
        d.task_spec = None
        return d

    spec: TaskSpec = d.task_spec
    if mode_selection in ("quick_search", "research", "dataset", "hybrid"):
        spec.mode = mode_selection  # type: ignore[assignment]
    if spec.mode in ("research", "hybrid") and spec.report is None:
        spec.report = ReportSpec(question=spec.scope.questions[0] if spec.scope.questions else spec.requirement_text)
    if spec.mode in ("dataset", "hybrid") and spec.dataset is None:
        # 缺字段定义无法执行数据任务：转澄清
        d.kind = "clarify"
        d.task_spec = None
        d.questions = d.questions or ["你希望表格包含哪些字段？每一行代表什么对象？"]
        return d
    if spec.mode == "quick_search":
        spec.dataset = None
    if not spec.scope.questions:
        spec.scope.questions = [spec.requirement_text]
    # 输出格式默认值
    if not spec.output_formats:
        spec.output_formats = {"quick_search": [], "research": ["md"], "dataset": ["csv", "xlsx"],
                               "hybrid": ["csv", "xlsx", "md"]}[spec.mode]  # type: ignore[assignment]
    # 数据/混合任务首次必须确认字段
    if spec.mode in ("dataset", "hybrid"):
        d.needs_confirmation = True
    if not d.plan_steps:
        d.plan_steps = ["规划搜索关键词", "用云端浏览器搜索并读取网页", "提取并核验信息", "整理成果"]
    return d


async def compile_turn(*, user_text: str, mode_selection: str, history: list[tuple[str, str]],
                       pending_spec_json: str | None, conversation_id: str | None) -> IntentDecision:
    prompt = build_prompt(user_text=user_text, mode_selection=mode_selection, history=history,
                          pending_spec_json=pending_spec_json, today=date.today().isoformat())
    decision = await run_agent(SPEC, prompt, conversation_id=conversation_id)
    return normalize_decision(decision, mode_selection)
