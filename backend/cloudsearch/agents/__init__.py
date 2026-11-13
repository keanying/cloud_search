"""八个智能体，各自独立子包：

requirement_compiler  需求编译   识别意图/澄清/生成 TaskSpec
coordinator           协调       DAG阶段规划（程序）+ 覆盖度评估与补查决策（模型）
search_planner        搜索规划   生成搜索词矩阵
browser_researcher    浏览研究   程序化读页 + 必要时由模型决定交互动作
extractor             信息抽取   从实读正文抽取事实/字段与逐字摘录
verifier              核验       摘录逐字校验（程序）+ 跨来源冲突检查（模型）
analyst               分析       生成受限计算方案，DuckDB 确定性执行
report_writer         报告写作   带 [n] 引用的回答/报告，引用由程序校验
"""

from .base import ROLE_INFO, AgentRole, AgentSpec, run_agent

__all__ = ["ROLE_INFO", "AgentRole", "AgentSpec", "run_agent"]
