# 第 03 轮：PDF、OCR 与版本变化

```text
执行第03轮：在安全规定链路上增加PDF/附件、OCR、页码证据和版本差异。

读取：docs/codex-kit/docs/02-content-model.md、docs/codex-kit/docs/04-data-source-compliance.md、docs/codex-kit/docs/08-security-threat-model.md、docs/codex-kit/docs/09-operations-runbook.md。

必须交付：
- PDF文本块、页码和坐标模型；扫描PDF OCR适配器；
- 附件树、文件安全扫描、页数/大小/解压上限；
- document_version和version_change完整状态；
- 文本归一化、内容哈希、元数据变化与实质变化区分；
- PDF证据在详情和审核页按页定位并高亮；
- 新版本导致旧Claim、摘要和发布快照进入UPDATE_DETECTED/RE_REVIEW_PENDING；
- AMENDS、SUPERSEDES候选关系，必须人审确认；`REPEALED` 是法规状态，不是文档关系，必须由官方证据支持并经有权审核确认；
- 差异查看器、版本时间线和撤回状态；
- 普通PDF、扫描PDF、表格、错误MIME、恶意动作、超大文件黄金样本；
- 指标：PDF解析率、OCR可用率、关键字段低置信数、版本变化数。

测试重点：
- PDF页码证据在重放后稳定；
- 扫描件低置信关键字段不能发布；
- 仅页眉变化不触发实质复核；
- 正文、文号、实施日期变化触发摘要失效；
- 原文撤回前台显示撤回且保留历史；
- PDF脚本、外链启动和压缩炸弹被隔离。

验收场景：用v1、元数据变化v2、实质修订v3和撤回四个固定样本演示完整生命周期。

不做：事故生命周期、语义去重、真实LLM。
```
