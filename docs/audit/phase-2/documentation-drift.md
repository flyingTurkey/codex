# 第12轮文档漂移

| 声明/预期问题 | 实际证据 | 结论 |
|---|---|---|
| README仍描述Round00 | HEAD `c9ffd4b` 的README已写“Round 00—11”，并区分第11轮工程PASSED/生产BLOCKED；由`9bd011f`更新 | `NOT_REPRODUCED`；用户要求的检查项已记录，不伪造漂移 |
| 二阶段方案路径引用不一致 | 总规范自引用和README均使用实际路径 `docs/codex-kit/docs/phase-2/SRBG-Phase-2-Optimization-Codex-Spec.md`；`9bd011f`修正 | `NOT_REPRODUCED`；历史问题已修复 |
| 第11轮工程PASSED等于生产READY | README、CHANGELOG和Round11验收均明确生产BLOCKED | 文档一致；运行严格金标门禁仍BLOCKED |
| Worker支持统一多来源生产调度 | 架构文档描述scheduler/collector目标；代码Beat只有MEM任务，DB运行全为Fixture | 文档目标与实现存在漂移 |
| 来源ACTIVE意味着真实获批运行 | 本地DB有54 ACTIVE，但全为固定/集成测试来源；46种子仍CANDIDATE | 验收/数据状态语义易误读，必须按证据重分类 |
| Round08已有300/100金标 | CHANGELOG称“首版内部固定金标结构”且注明未人工裁定；eval明确 `INTERNAL_TEST_FIXTURE` | 不是真人金标；严格gold manifest为0 |
| 普通用户依赖专用发布投影 | 架构/二阶段目标如此；实际普通API登录读取业务表，projection state当前0 | 未实现目标，非文档证明 |
| audit_log不可篡改 | 根约束使用强表述；实际为immutable trigger+应用hash，API/Worker可自造INSERT，无独立锚定，owner可重写 | 应统一表述为append-only/tamper-evident，绝非绝对不可篡改 |
| usage_event不保存浏览历史 | Round11新代码写匿名聚合桶；旧表仍有250条带actor_id的SEARCH | 验收只描述新路径，遗漏历史数据治理 |
| Smoke验证运行契约 | `smoke.py`期待旧两字段版本对象；当前契约增加search schema和semantic flag | 测试脚本漂移，退出2 |
| Round02—04专项仍可运行 | target隔离库停在0009，当前查询引用0010表 | 三个专项target漂移，退出2 |

## 提交状态差异

第11轮实现、二阶段文档基线和见证提交已经独立形成连续提交，工作树在第12轮进入时干净；分支名仍为 `codex/round-10-feed-search-daily`，名称落后于实际Round11/Phase2状态，但不改变提交内容。
