# analyst 分析

**职责**：针对固定的数据快照制定计算方案；**计算由程序执行**。

- 模型输出受限 DSL（AnalysisPlan）：group_by、count/count_distinct/sum/avg/min/max、过滤、排序、limit
- compute.py 校验字段与类型后编译为参数化 SQL，在内存 DuckDB 执行；不接受任意 SQL/脚本
- 缺失值不当 0；无法转为数字的值按空值处理并给出警告
- 结果（含实际执行的 SQL）进入报告与数据文件，报告中的数字必须来自这些结果
