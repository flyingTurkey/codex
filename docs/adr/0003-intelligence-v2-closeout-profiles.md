# ADR-0003：土木工程情报 v2 双验收 Profile

状态：Accepted
日期：2026-07-19

## 背景

原 v2 closeout 只表达生产切换前验收，要求 24 小时 AI 运行、Owner 人工标注、每源 72 小时及首批 14 天观察。现阶段需要一个更短的工程闭环验证，但不得将工程验证误报为生产就绪，也不得通过伪造外部事实取得 GO。

## 决策

closeout 必须显式选择以下 profile，缺省选择无效：

- `ENGINEERING_CLOSEOUT`：AI 连续运行至少 1 小时且至少一次真实 Schema 成功；20 个来源可并行观察，每源至少 1 小时；不要求 qualification 或 Feed 人工标注。Feed 仍须对同一真实 v2 快照的至少 200 条投影执行服务端结构审计，R4、未接受 claim 和无证据事实泄漏必须为零。
- `PRODUCTION_CLOSEOUT`：保留原 24 小时、至少五次真实 Schema 成功、360 条 Owner gold、200 条人工 Feed 抽检、每源 72 小时和首批 14 天后启动第二批的规则。

两个 profile 均保留 AI 补偿验收、20/20 来源结论、全部合规硬门禁、工程门禁和只读归档预检。来源评估不得自动启用生产来源；closeout 不执行迁移、调度或代际切换。

readiness manifest 必须记录 profile 及其独立规则版本。同一份工程证据可以得到 engineering `GO`，但在 production profile 下仍必须 `NO_GO`。

## 影响

`ENGINEERING_CLOSEOUT/GO` 只表示当前工程基线通过，不表示可以切换生产。生产授权仍以 `PRODUCTION_CLOSEOUT/GO` 为前置条件。任何真实环境、DeepSeek、来源、Feed、补偿或归档证据缺失时，对应 profile 均失败关闭。
