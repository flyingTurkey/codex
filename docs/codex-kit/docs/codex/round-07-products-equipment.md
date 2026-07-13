# 第 07 轮：软件、物联网、低空和 AI 设备

```text
执行第07轮：建立技术产品统一模型并完成软件、物联网、低空和AI设备展示。

读取：docs/codex-kit/docs/01-PRD.md、docs/codex-kit/docs/02-content-model.md、docs/codex-kit/assets/taxonomy.yaml、docs/codex-kit/assets/ui/copy_examples.md、docs/codex-kit/docs/08-security-threat-model.md。

来源：至少一个软件厂商和一个低空/设备厂商固定样本；真实来源必须通过来源准入。

必须交付：
- technology_product_profile及vendor、product、model实体；
- product_kind、型号、能力、接口、部署方式、场景、案例、证据等级；
- promotional_claims与verified_capabilities分离；
- 产品与数字化案例的APPLIED_IN关系；
- 软件、物联网、低空、AI设备四类筛选和差异化字段；
- 产品详情显示“产品能力/工程证据/许可与限制”三区；
- 低空产品固定合规提示：产品发布不代表空域、适航、飞手和项目许可；
- 产品版本和型号归一候选，人工合并入口；
- 厂商图片默认不下载，使用占位素材；
- 契约、门禁、E2E和无障碍测试。

硬性测试：
- 厂商宣称不进入verified_capabilities；
- 产品页不能自动产生“适用于四川路桥采购”结论；
- 同名不同型号不被错误合并；
- 型号版本更新不覆盖历史；
- 低空设备无许可证据时许可字段为UNKNOWN。

验收：四类产品均可通过统一API和卡片显示，类型字段正确，厂商声明与独立证据视觉和数据层均分离。

不做：价格采集、采购比选、设备远程接入、飞行审批。
```
