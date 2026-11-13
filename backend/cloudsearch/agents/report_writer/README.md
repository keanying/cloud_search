# report_writer 报告写作

**职责**：基于已核验证据与计算结果，撰写带 [n] 引用的简答（quick_search）或报告（research/hybrid）。

- 输入：问题、提纲、按来源分组的证据、analyst 计算结果表、冲突与缺口
- 输出：ReportDraft（标题、Markdown、局限）
- 程序校验：`sanitize_citations` 删除不存在的引用序号，统计实际使用的来源
- 边界：不搜索、不浏览、不写库；不新增无证数字/因果/权利声明；冲突如实呈现
