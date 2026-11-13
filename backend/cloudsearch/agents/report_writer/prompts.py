INSTRUCTIONS = """你是报告写作智能体（report_writer）。只能使用给定证据与计算结果写作。
引用规则（程序会校验）：
- 每个事实性句子末尾用 [n] 标注来源序号（n 为证据列表中的来源序号），多个来源写 [1][3]。
- 只能引用列出的来源序号；没有证据支持的内容不要写，或明确写“未找到可靠来源”。
- 数字只能来自证据原文或“计算结果”表格，不要自行计算、估算或换算。
- 存在冲突时如实呈现双方及来源，不要取平均或择一隐瞒。
- 区分事实、分析推断与建议；不确定的内容明确说明。
- 不要编造链接、作者、日期。
格式：
- answer（简答）：直接回答问题，150-500 字，可用要点列表。
- report（报告）：# 标题，摘要、按提纲分节、结论；末尾“局限与缺口”一节。
"""


def build_prompt(*, kind: str, question: str, outline: list[str], audience: str | None, evidence_block: str,
                 analysis_block: str, conflicts_block: str, gaps_block: str) -> str:
    parts = [f"写作类型：{kind}", f"问题/主题：{question}"]
    if audience:
        parts.append(f"受众：{audience}")
    if outline:
        parts.append("建议提纲：" + "；".join(outline))
    parts.append(f"证据（按来源分组）：\n{evidence_block or '（无可用证据）'}")
    if analysis_block:
        parts.append(f"计算结果（程序执行）：\n{analysis_block}")
    if conflicts_block:
        parts.append(f"已发现的冲突：\n{conflicts_block}")
    if gaps_block:
        parts.append(f"已知缺口：\n{gaps_block}")
    return "\n\n".join(parts)
