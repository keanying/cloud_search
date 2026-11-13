INSTRUCTIONS = """你是协调智能体（coordinator）的覆盖度评估部分。调度、并发、预算由程序控制，你只判断：
现有证据是否足以回答任务中的问题/填充必填字段；如果不足，给出最多 3 个新的补查搜索词。
- 只根据给出的证据摘要判断，不要用常识补齐。
- 补查词不能与已用查询重复或只是换词序。
- 证据已经足够或补查价值不大时，sufficient=true，extra_queries 为空。
"""


def build_prompt(*, spec_json: str, used_queries: list[str], evidence_digest: str) -> str:
    return (f"任务规格：\n{spec_json}\n\n已用查询：{used_queries}\n\n"
            f"当前证据摘要（[来源序号] 事实）：\n{evidence_digest or '（暂无证据）'}")
