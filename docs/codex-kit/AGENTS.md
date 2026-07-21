# AGENTS.md：历史 Codex Kit 作用域

本目录保存早期设计、原型、命令轮次和验收资产，主要用于历史溯源。它不再定义当前产品范围、API、权限、来源准入、AI、UI、测试或执行顺序。

## 当前任务必须遵守

1. 先完整阅读仓库根目录 `AGENTS.md`；根规则是本目录及其所有子目录的唯一现行产品与工程权威。
2. 再按根目录 `CONTEXT-MAP.md`、四个当前 Context、ADR、GitHub Spec #1 和当前 ticket 工作。
3. 本目录旧 PRD、Codex rounds、prompt、v1 Item 契约、企业/OIDC/多角色说明和旧门槛均为 Legacy，不得作为可执行需求或 production 配置。
4. 除非当前任务明确授权，不得继续运行本目录的 bootstrap/round 命令，不得从历史 fixture 或原型反推当前业务事实，不得把 prototype 代码提升为生产依赖。
5. 根规则明确引用的资产仍按其限定用途有效，例如 `assets/ui/design_tokens.json`、选定视觉参考和步骤 Schema；有效资产不使同目录其他历史文档自动恢复为现行规范。
6. 修改历史材料时保留其点时语义，并在顶部增加当前替代指针；不要把旧事实悄悄改写成今天的事实。

当前维护入口：`docs/operations/intelligence-v2-maintainer-guide.md`。当前生产状态和门槛必须以 GitHub Spec #1、Issue #36 及其原生依赖为准。
