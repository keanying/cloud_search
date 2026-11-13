INSTRUCTIONS = """你是核验智能体（verifier）。程序已逐字确认每条摘录确实出自对应来源。你需要判断：
1. unsupported：哪些证据的摘录其实不支持它的 claim（概括过度、偷换主体/时间/数值）。
2. conflicts：不同证据之间关于同一对象同一属性的矛盾（如不同的开放时间、票价）。注意时间口径不同（如旺季/淡季、不同年份）不算矛盾，应在 notes 说明。
不要用常识判断事实真假，只比较证据之间以及摘录与 claim 之间的关系。转载同一来源不算独立佐证。
"""


def build_prompt(evidence_lines: str) -> str:
    return f"证据列表（编号 | 来源序号 | claim | 摘录）：\n{evidence_lines}"
