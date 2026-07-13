# 第 04 轮：安全案例生命周期

```text
执行第04轮：完成安全事故从初报、续报、调查报告到处罚和整改的事件化展示。

读取：docs/codex-kit/docs/01-PRD.md、docs/codex-kit/docs/02-content-model.md、docs/codex-kit/assets/taxonomy.yaml、docs/codex-kit/assets/sample_items.json、docs/codex-kit/docs/08-security-threat-model.md。

必须交付：
- safety_case_profile、event、event_item、event_relation、claim_conflict迁移；
- 事故类型、工程类型、时间、地区、伤亡、损失、调查状态字段；
- 初报/续报/正式调查/处罚/整改独立内容类型或子状态；
- 基于日期、地区、项目、主体和事故类型的事件关联候选；
- 关键字段冲突工作台；
- 原因、责任、伤亡和损失只能来自正式证据并强制人工审核；
- 安全案例列表、详情、已确认事实区、待核实区和时间线；
- 相似场景和防范措施先使用受控标签，不生成现场操作指令；
- 从官方通报和调查报告固定样本完成E2E；
- 撤回、更正和后续关系审计。

硬性测试：
- 同一事故不同阶段不被精确或近似去重删除；
- 媒体推测不能写入official_direct_causes；
- 无正式调查证据的责任字段为null；
- 伤亡数字冲突进入人工队列；
- 事故未结案显著显示调查中；
- 提交人不能审批自己的安全案例。

验收：演示一组初报→续报→调查→整改固定样本，时间线和证据完整，所有R3精选均经过审核。

不做：媒体线索自动发布、事故等级模型推断、复杂AI摘要。
```
