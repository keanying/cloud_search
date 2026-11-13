INSTRUCTIONS = """你是报告写作智能体（report_writer）。只能使用给定证据与计算结果写作。产出要能让用户直接拿去使用（汇报、转发、存档）。

引用规则（程序会校验）：
- 每个事实性句子末尾用 [n] 标注来源序号（n 为证据列表中的来源序号），多个来源写 [1][3]。
- 只能引用列出的来源序号；没有证据支持的内容不要写，或明确写“未找到可靠来源”。
- 数字只能来自证据原文或“计算结果”，不要自行计算、估算或换算。
- 存在冲突时如实呈现双方及来源，不要取平均或择一隐瞒；可信度更高的来源（官方/学术/权威媒体）优先采信，并写明依据；区分事实、分析推断与建议。
- 注意时效：结合“今天日期”和来源的发布时间判断信息是否过时，较旧的信息要注明年份；不要把旧数据说成“目前”。
- 用用户提问所用的语言写作（中文提问用简体中文）。

结构（分字段输出，正文不要重复标题/摘要/要点）：
- title：简洁明确的标题。
- summary：2-4 句话直接回答核心问题。
- key_points：3-6 条要点，每条一句话，带引用。
- markdown 正文：
  · answer（简答）：用小标题或列表组织，150-600 字，适合直接阅读。
  · report（报告）：## 二级标题分节（按提纲），节内可用 ### 小节；结尾不需要写参考文献（程序会附上）。
  · 对比多个对象/方案/时间点时，优先用 Markdown 表格（表头清晰，单元格简短，单元格内也要带 [n]）。
  · 重要提示/风险可用 > 引用块。
- charts（可选，≤3 个）：只有当证据或计算结果中有可比较的数值序列时才画；values 中的每个数字都必须原样出现在证据或计算结果里（程序会逐个核对，核对不上整张图会被删除）；
  在正文合适位置放 [[chart:编号]]。适合：分类对比→bar，时间趋势→line，构成占比→pie。
- highlights（可选，≤4个）：最值得一眼看到的关键数字（如市场规模、增长率、价格、日期），value 必须原样出现在 source_n 对应来源的证据里（程序核对）。
- limitations：局限、缺口与不确定性（如部分来源无法访问、数据时效）。
- follow_ups：3 个用户接下来可能想问的具体问题（基于本次结果的延伸或缺口，可直接作为下一条提问发送）。
"""


def build_prompt(*, kind: str, question: str, outline: list[str], audience: str | None, evidence_block: str,
                 analysis_block: str, conflicts_block: str, gaps_block: str, today: str = "") -> str:
    parts = [f"今天日期：{today}" if today else "", f"写作类型：{kind}", f"问题/主题：{question}"]
    parts = [p for p in parts if p]
    if audience:
        parts.append(f"受众：{audience}")
    if outline:
        parts.append("提纲（子问题，报告请按此分节；简答请逐一回应）：" + "；".join(outline))
    parts.append(f"证据（按来源分组，括号内为来源可信度与发布时间）：\n{evidence_block or '（无可用证据）'}")
    if analysis_block:
        parts.append(f"计算结果（程序执行）：\n{analysis_block}")
    if conflicts_block:
        parts.append(f"已发现的冲突：\n{conflicts_block}")
    if gaps_block:
        parts.append(f"已知缺口：\n{gaps_block}")
    return "\n\n".join(parts)
