"""确定性阶段规划：四种模式的 DAG 阶段（程序决定，不由模型决定）。"""

from __future__ import annotations

STAGE_LABELS: dict[str, str] = {
    "files": "读取文件",
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


WEB_STAGES = ("plan", "search", "read", "coverage")


def stages_for(mode: str, *, has_analysis: bool = False, has_files: bool = False, use_web: bool = True) -> list[str]:
    stages = list(MODE_STAGES[mode])
    if mode == "dataset" and has_analysis:
        stages.append("analyze")
    if has_files:
        if not use_web:  # 只基于上传文件：不规划搜索、不联网
            stages = [st for st in stages if st not in WEB_STAGES]
        stages.insert(0, "files")
    return stages


def stages_for_spec(spec: dict) -> list[str]:
    """按任务规格（字典）计算阶段（进度展示与执行共用）。"""
    ds = spec.get("dataset") or {}
    scope = spec.get("scope") or {}
    files = bool(scope.get("file_ids"))
    use_web = scope.get("use_web")
    return stages_for(spec.get("mode", "quick_search"), has_analysis=bool(ds.get("analysis_request")),
                      has_files=files, use_web=(use_web if use_web is not None else not files))
