# ADR-0003：土木工程情报 v2 双验收 Profile

状态：Accepted
日期：2026-07-19

## 背景

原 v2 closeout 只表达生产切换前验收。现阶段需要一个更短的工程闭环验证，但不得将工程验证误报为生产就绪，也不得通过伪造外部事实取得 GO。运行时长、样本量和观察窗口属于会随验证经验调整的版本化验收规则，不应由 ADR 充当配置源。

## 决策

closeout 必须显式选择以下 profile，缺省选择无效：

- `ENGINEERING_CLOSEOUT`：用较短的真实运行与自动结构审计证明工程链路可闭环；不要求 production Owner Gold 或 Feed 人工精度授予，且永不授权生产切换。
- `PRODUCTION_CLOSEOUT`：消费当前版本化生产验收规则中的真实 AI、Owner Gold、Feed Owner 抽检、来源波次和组合窗口证据；任一证据不足都失败关闭。

两个 profile 均保留 AI 补偿验收、20/20 来源结论、全部合规硬门禁、工程门禁和只读归档预检。来源评估不得自动启用生产来源；closeout 不执行迁移、调度或代际切换。

readiness manifest 必须记录 profile、独立规则版本和实际解析出的数值门槛。同一份工程证据可以得到 engineering `GO`，但在 production profile 下仍必须 `NO_GO`。现行数值以 GitHub Spec #1 的“Owner 生产收口门槛”和对应 ticket 为准；修改数值必须先更新版本化规则与 TDD，不能只改文档或运行参数。

## 影响

`ENGINEERING_CLOSEOUT/GO` 只表示当前工程基线通过，不表示可以切换生产。生产授权仍以 `PRODUCTION_CLOSEOUT/GO` 为前置条件。任何真实环境、DeepSeek、来源、Feed、补偿或归档证据缺失时，对应 profile 均失败关闭。

具体 campaign 命令、活动生命周期、故障注入、采样 cutoff 和当前运行结果属于可逆的验收实现与操作证据，不由本 ADR 冻结；它们记录在本轮验收记录和工程收口 handoff 中。未来可替换这些机制，但不得弱化本 ADR 对两个 profile 的语义隔离和失败关闭要求。

## 2026-07-20 边界澄清

Production Owner Gold 必须使用真实 `HUMAN_OWNER` 标注和在标注前独立封存的预测；结构回放、pilot、fixture 或模型生成标签不能签发生产授予。具体 corpus 数量、分层、类型覆盖和质量阈值由版本化生产规则及 Issue #36 管理。历史 corpus 的 `NO_GO`、退役或重新冻结属于验收事实，记录在对应验收文件，不改变本 ADR 的 profile 隔离与失败关闭决定。
