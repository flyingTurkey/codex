# Evidence-grounded Summary Prompt v1

任务：依据已经接受的 Claim 和 Evidence，为四川路桥内部用户生成摘要。

输入：

```json
{{accepted_claims_and_evidence}}
```

必须输出：

- `one_sentence`：发生了什么，80 个汉字以内；
- `why_it_matters`：为什么可能与四川路桥有关，120 个汉字以内；
- `key_points`：最多 5 条；
- `applicable_scenarios`：适用工程阶段和专业；
- `limitations`：证据缺口、适用边界和核验事项；
- `recommended_actions`：只允许 `READ_ORIGINAL`、`PROFESSIONAL_REVIEW`、`SAVE`、`FOLLOW`、`TECHNICAL_RESEARCH`。
- `used_claim_ids`：列出摘要实际使用的已接受 Claim；不得为空。

禁止：

- 使用无证据的绝对化或营销化结论；
- 把企业自述改写成平台认定；
- 生成原文没有的性能指标、比例、金额、日期或伤亡；
- 独立判断事故责任、违法性或法规适用；
- 大段复述原文；
- 提供现场操作、安全处置、采购或法律结论。

结果必须符合 `assets/schemas/summarize-output.schema.json`。
