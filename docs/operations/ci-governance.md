# CI 与仓库治理配置

`main` 必须按 `branch-protection.example.json` 配置分支保护，启用管理员同样受保护、最新分支、两人审批、CODEOWNERS 审批、限制直接推送、禁止强推和删除。六个工程状态检查均为 required checks。

`CODEOWNERS.example` 仅是待仓库管理员替换的模板。占位团队未被擅自写入活动 `.github/CODEOWNERS`，因此当前证据包必须保持 `BLOCKED`，直到管理员填写真实团队、提交活动配置并导出 GitHub 分支保护 API 响应作为原始证据。

候选输出不得作为检查输入：金标与策略从版本控制中的固定路径读取，readiness 清单重新计算自身哈希并逐项验证证据引用。`evidence-integrity` 接受诚实的 `BLOCKED` 并验证其不可被写成 READY；严格 `make golden-replay` 和 `make readiness-evidence` 继续以非零退出码阻止试点/生产晋级，不属于普通 PR 的工程成功条件。任何金标、策略、工作流、readiness Schema 或验收证据变更都要求质量、安全或验收所有者审核。
