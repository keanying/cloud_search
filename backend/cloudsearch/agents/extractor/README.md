# extractor 信息抽取

**职责**：从一个已实际读取的来源正文中，抽取与任务相关的事实（Finding）或数据行（RecordCandidate），每条都附逐字原文摘录。

- 输入：TaskSpec、单个 SourceDoc（截断到 14000 字）
- 输出：ExtractionOutput（relevant / findings / records）
- 工具：无；需要新资料时由流水线另行读取，不能自行联网
- 边界：提取成功只表示形成候选，**不表示已核验**；摘录由 verifier 逐字校验，缺值保留 null + 原因，不得用常识补齐
