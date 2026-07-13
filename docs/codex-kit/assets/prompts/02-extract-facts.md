# Fact and Evidence Extraction Prompt v1

任务：从文档中抽取原子事实，并将每个事实绑定到证据。

- `item_type={{item_type}}`
- `field_schema={{content_type_specific_schema}}`

<document>
{{document_with_block_and_page_ids}}
</document>

规则：

- 一个 Claim 只表达一个事实；
- 精确抽取名称、日期、文号、标准号、地点、金额、单位、产品型号和项目阶段；
- 保留原值并提供规范化值；
- 相对日期只有在发布时间明确时才换算；
- OCR不清、单位缺失、语义含糊或前后冲突时标记 `UNVERIFIED` 或 `CONFLICTING`；
- 事故原因和责任只能抽取正式认定语境；
- “据称、预计、力争、领先、国际先进”等表述标为 `REPORTED_CLAIM`；
- 不从产品页推导适航、认证、许可或特定工程适用资格；
- 每个高影响事实必须有 `evidence_id`；
- 证据片段采用最短充分长度并给出页码、段落、坐标或表格位置；
- 多来源冲突分别保留，不自行裁决。
- 模型输出只产生候选 Claim 和 Evidence，不产生来源权威、最终证据角色、分数、风险、审核状态或发布状态；结果必须符合 `assets/schemas/extract-output.schema.json`。
