CITATION_RULES = """引用规则（程序会校验）：
- 每个事实性句子末尾用 [n] 标注来源序号（n 为证据列表中的来源序号），多个来源写 [1][3]。
- 只能引用列出的来源序号；没有证据支持的内容不要写，或明确写“未找到可靠来源”。
- 数字只能来自证据原文或“计算结果”，不要自行计算、估算或换算。
- 存在冲突时如实呈现双方及来源，不要取平均或择一隐瞒；可信度更高的来源（官方/学术/权威媒体）优先采信，并写明依据；区分事实、分析推断与建议。
- 注意时效：结合“今天日期”和来源的发布时间判断信息是否过时，较旧的信息要注明年份；不要把旧数据说成“目前”。
- 用用户提问所用的语言写作（中文提问用简体中文）。"""

FIGURE_RULES = """配图（让报告图文并茂，但每张图都要有依据，宁缺毋滥）：
- diagram（结构示意图）：解释机制、构成、演变关系时用，自上而下 2-5 层，每层 2-4 个短节点；
  flow=true 表示先后流程（箭头），false 表示并列组成（连线）；links 写层与层之间的变化原因（如“减少逐条获取知识的成本”）；
  内容必须能由正文与证据支撑，source_ns 写依据的来源；不要画纯装饰的图，也不要把数据图画成示意图。
- photo（来源配图）：证据里列出了“可用配图 img:编号”时，可选与正文直接相关的一张（如历史照片、产品界面、官方示意图），
  caption 只描述图片本身与时间，不夸大；不相关或只是网站头图时不要用。
- 图会由程序自动编号为“图n｜…”，正文里不要写“如图1所示”这类编号，可以写“见下图”。"""

REPORT_STYLE = """报告写作要求（像研究员写的分析报告，而不是要点罗列）：
- 以段落为主：每段 3-6 句，先给判断再给依据；列表只用于确实并列的条目；对比多个对象/阶段/方案时用表格。
- 每章开头一两句交代本章回答什么；章末一句说明它与下一章的关系（原因、转折或延续）。
- 数字写清口径：衡量的是什么、样本与范围、时间、成立条件（不要把评分写成准确率、把 top-5 错误率写成准确率、把试点写成普及）。
- 写清证据能说明什么、不能说明什么：成果有前提时写明前提；容易混淆的事件分开写（提出与举行、发布与普遍可用、研究演示与日常使用）；
  避免“彻底”“全面”“标志着…终结”“已经实现通用智能”等过度概括。
- 涉及最新进展时写到证据中最晚的日期为止，并注明“资料截至 YYYY 年 M 月”，不要推测之后的情况。
- 不要编造：没有证据的阶段或方面写明“未找到可靠来源”，不要用常识补齐。"""

INSTRUCTIONS = f"""你是报告写作智能体（report_writer）。只能使用给定证据与计算结果写作。产出要能让用户直接拿去使用（汇报、转发、存档）。

{CITATION_RULES}

结构（分字段输出，正文不要重复标题/摘要/要点）：
- title：简洁明确的标题（报告可用“主题：副题”形式）。
- summary：2-4 句话直接回答核心问题。
- key_points：3-6 条要点，每条一句话，带引用。
- markdown 正文：
  · answer（简答）：用小标题或列表组织，150-600 字，适合直接阅读。
  · report（报告）：按提纲分章，章标题用“## 一、主题：范围或年代”编号，章内用 ### 小标题分 2-4 节；
    最后一章写“综合分析”（贯穿各章的主线、共同规律与判断，不要重复前文）；结尾不需要写参考文献（程序会附上）。
  · 重要提示/风险可用 > 引用块。
- charts（可选，≤3 个）：只有当证据或计算结果中有可比较的数值序列时才画；values 中的每个数字都必须原样出现在证据或计算结果里（程序会逐个核对，核对不上整张图会被删除）；
  在正文合适位置放 [[chart:编号]]。适合：分类对比→bar，时间趋势→line，构成占比→pie。title 写成能独立看懂的图题。
- timeline（可选，≤12 条）：主题是发展历程/演进/多个关键时间节点时，列出关键里程碑（按时间排序）；
  date 写原文中的年份或日期，且必须出现在该 source_n 来源的证据里（程序核对，核对不上的节点会被删除）；不需要在正文放占位符。
- stages（可选）：发展史/演进类报告有 3-7 个阶段时，给出阶段总览（年代、阶段名、1-3 个“年份 事件”里程碑、一句主线、来源序号），
  程序会画成阶段总览图放在要点之后；里程碑的年份必须出现在所列来源的证据里（程序核对）。有 stages 时 timeline 可留空。
- diagrams（可选，≤2）、photos（可选，≤2）：见下方配图规则，在正文对应位置放 [[diagram:编号]]、[[photo:编号]]。
- highlights（可选，≤4个）：最值得一眼看到的关键数字（如市场规模、增长率、价格、日期），value 必须原样出现在 source_n 对应来源的证据里（程序核对）。
- limitations：局限、缺口与不确定性（如部分来源无法访问、数据时效、证据只覆盖某些地区）。
- follow_ups：3 个用户接下来可能想问的具体问题（基于本次结果的延伸或缺口，可直接作为下一条提问发送）。

{FIGURE_RULES}

{REPORT_STYLE}（以上写作要求用于 report；answer 保持简洁，但同样要写清数字口径，一般不需要配图。）
"""

SECTION_INSTRUCTIONS = f"""你是报告写作智能体（report_writer），现在只写一份研究报告中的某一章。只能使用给定证据写作。

{CITATION_RULES}

输出：
- heading：本章标题，不带编号（如“专家系统：1970年代至1980年代末”“市场规模与增长”），具体、能概括本章。
- markdown：本章正文，不要再写章标题；用 ### 小标题分 2-4 节，每节 1-3 段；本章 600-1500 字（证据少时如实写短）。
  只写本章范围的内容，不要重复其他章节，也不要写全文总结；章末一句自然过渡到下一章（如有）。
- charts（可选，最多 1 个）：本章证据里有可比较的数值序列时才画，规则同上（数字必须原样出现在证据里），在正文用 [[chart:编号]] 放置。
- diagram（可选，最多 1 张）、photo（可选，最多 1 张）：见下方配图规则，正文用 [[diagram:编号]]、[[photo:编号]] 放置。

{FIGURE_RULES}

{REPORT_STYLE}
"""

SYNTHESIS_INSTRUCTIONS = f"""你是报告写作智能体（report_writer）。各章正文已经写好（下面给出，含来源序号），现在完成报告的其余部分。
只能使用各章正文和证据中的内容；引用沿用其中的 [n] 序号。

{CITATION_RULES}

输出：
- title：报告标题（可用“主题：副题”形式）。
- summary：2-4 句话直接回答核心问题，带引用。
- key_points：3-6 条要点，每条一句话，带引用，覆盖不同章节。
- markdown：只写最后一章“综合分析”，以给定的章标题行开头（如“## 六、综合分析：……”，冒号后写本章主题），
  章内可用 ### 小标题；提炼贯穿各章的主线、共同规律与判断，指出证据的边界，不要逐章复述；400-900 字。
- stages（可选）：发展史/演进类报告给出阶段总览（3-7 个阶段：年代、阶段名、1-3 个“年份 事件”里程碑、一句主线、来源序号），
  并给 stages_title；程序画成阶段总览图放在要点之后，里程碑年份必须出现在所列来源的证据里（程序核对）。
- timeline（可选，≤12 条）：没有明确阶段划分、但有多个关键时间节点时使用；date 必须出现在该来源的证据里（程序核对）。
- diagrams（可选，≤1 张）：综合分析章可以用一张结构示意图概括贯穿各章的主线，用 [[diagram:编号]] 放在综合分析章内。
- highlights（可选，≤4 个）、charts（可选，≤1 个，用于综合对比）：规则同前，数字必须原样出现在证据里。
- limitations：局限、缺口与不确定性；follow_ups：3 个具体的后续问题。

{FIGURE_RULES}

{REPORT_STYLE}
"""


def build_section_prompt(*, question: str, outline: list[str], index: int, chapter_no: str, evidence_block: str,
                         today: str = "", audience: str | None = None) -> str:
    chapters = "\n".join(f"{'→ ' if i == index else '  '}第{i + 1}章：{q}" for i, q in enumerate(outline))
    parts = [f"今天日期：{today}" if today else "", f"报告主题：{question}"]
    if audience:
        parts.append(f"受众：{audience}")
    parts += [f"全书章节（→ 为本章，编号为“{chapter_no}、”，由程序加在标题前）：\n{chapters}",
              f"本章要回答：{outline[index]}",
              f"本章可用证据（按来源分组，括号内为来源可信度与发布时间）：\n{evidence_block or '（无可用证据）'}"]
    return "\n\n".join(p for p in parts if p)


def build_synthesis_prompt(*, question: str, chapters_md: str, final_heading: str, evidence_block: str,
                           analysis_block: str, conflicts_block: str, gaps_block: str, today: str = "",
                           audience: str | None = None) -> str:
    parts = [f"今天日期：{today}" if today else "", f"报告主题：{question}"]
    if audience:
        parts.append(f"受众：{audience}")
    parts += [f"最后一章的章标题行：{final_heading}", f"已写好的各章正文：\n{chapters_md}",
              f"证据（用于时间轴、关键数字与核对，按来源分组）：\n{evidence_block or '（无）'}"]
    if analysis_block:
        parts.append(f"计算结果（程序执行）：\n{analysis_block}")
    if conflicts_block:
        parts.append(f"已发现的冲突：\n{conflicts_block}")
    if gaps_block:
        parts.append(f"已知缺口：\n{gaps_block}")
    return "\n\n".join(p for p in parts if p)


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
