INSTRUCTIONS = """你是分析智能体（analyst）。你只制定计算方案，计算由程序在数据库中确定性执行，你不能自己算数。
- 只能使用给定字段；数值聚合（sum/avg/min/max）只能用于 number/integer 字段。
- 每个分析要回答用户的分析需求或对报告有明确价值；最多 5 个。
- 缺失值不会被当作 0；如需统计缺失，用 filters 的 is_null。
"""


def build_prompt(*, request: str, entity: str, fields_desc: str, sample: str, row_qty: int) -> str:
    return (f"分析需求：{request}\n记录粒度：{entity}\n行数：{row_qty}\n字段：\n{fields_desc}\n\n"
            f"样例行（JSON）：\n{sample}")
