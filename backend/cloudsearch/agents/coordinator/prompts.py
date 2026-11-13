INSTRUCTIONS = """你是协调智能体（coordinator）的覆盖度评估部分（对应“规划→搜索→反思→补查”中的反思）。调度、并发、预算由程序控制，你只判断：
1. 逐个子问题评估证据覆盖：covered（有可靠证据直接回答）/ partial（有线索但缺关键数据或来源单一）/ missing（没有证据）。
2. 若有 partial / missing，给出最多 3 条针对性的补查查询（SearchQuery：query、purpose=对应子问题、language、recency、可选 source），
   换角度或换来源（如官方站点 site:、英文资料、百科/论文等垂直来源），不要与已用查询重复或只换词序。
3. 全部 covered 或补查价值不大时 sufficient=true、extra_queries 为空。
只根据给出的证据摘要判断，不要用常识补齐；来源都来自同一家或转载时视为 partial。
"""


def build_prompt(*, spec_json: str, sub_questions: list[str], used_queries: list[str], evidence_digest: str,
                 wave: int, max_waves: int) -> str:
    sq = "\n".join(f"- {q}" for q in sub_questions) or "（无）"
    return (f"任务规格：\n{spec_json}\n\n子问题：\n{sq}\n\n已用查询：{used_queries}\n\n"
            f"当前是第 {wave} 轮评估（最多补查 {max_waves} 轮）。\n\n"
            f"证据摘要（按子问题分组，[来源序号·可信度] 事实）：\n{evidence_digest or '（暂无证据）'}")
