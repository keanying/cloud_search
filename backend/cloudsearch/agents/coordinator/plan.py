"""确定性阶段规划：四种模式的 DAG 阶段（程序决定，不由模型决定）。"""

from __future__ import annotations

STAGE_LABELS: dict[str, str] = {
    "plan": "规划搜索",
    "search": "浏览器搜索",
    "read": "读取网页",
    "extract": "提取信息",
    "coverage": "评估覆盖/补查",
    "verify": "核验来源",
    "build": "整理数据",
    "analyze": "计算分析",
    "write": "撰写成果",
}

MODE_STAGES: dict[str, list[str]] = {
    "quick_search": ["plan", "search", "read", "extract", "verify", "write"],
    "research": ["plan", "search", "read", "extract", "coverage", "verify", "write"],
    "dataset": ["plan", "search", "read", "extract", "coverage", "verify", "build"],
    "hybrid": ["plan", "search", "read", "extract", "coverage", "verify", "build", "analyze", "write"],
}

# 补查最多一轮、最多 3 个查询，防止“证据不足”无限递归
MAX_EXTRA_WAVES = 1
MAX_EXTRA_QUERIES = 3


def stages_for(mode: str, *, has_analysis: bool = False) -> list[str]:
    stages = list(MODE_STAGES[mode])
    if mode == "dataset" and has_analysis:
        stages.append("analyze")
    return stages
