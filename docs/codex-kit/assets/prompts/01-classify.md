# Classification Prompt v1

任务：按照 `taxonomy_version={{taxonomy_version}}` 对文档分类。

允许标签：

```json
{{controlled_taxonomy_json}}
```

来源元数据：

- `source_name={{source_name}}`
- `source_authority={{source_authority}}`
- `canonical_url={{canonical_url}}`
- `published_at={{published_at}}`

<document>
{{normalized_document_text}}
</document>

要求：

- 只能选择允许标签；
- 输出一个 `channel` 和一个 `item_type`；
- 可输出多个工程专业、生命周期、技术和场景标签；
- 标签置信度低于 0.60 时不输出；
- 无法判断整个文档时，分类候选可使用 `UNKNOWN`；`UNKNOWN` 不能进入正式内容 Schema 和发布流程；
- 事故初报、调查报告、处罚和整改不得混为一类；
- 企业产品发布不得分类为独立验证的工程成效；
- 分类理由不得引入原文外知识；
- 结果必须符合 `assets/schemas/classify-output.schema.json`。
