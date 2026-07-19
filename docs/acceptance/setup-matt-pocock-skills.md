# Matt Pocock Skills 仓库配置验收

验收日期：2026-07-19

## 范围

- 将工程 Skills 的 issue tracker 固定为 GitHub 仓库 `flyingTurkey/codex`。
- 使用默认五项 triage 标签。
- 使用以根 `CONTEXT-MAP.md` 为入口的 multi-context 领域文档布局。
- 本轮只修改仓库协作配置与文档，不修改业务代码、数据库、运行配置或测试阈值。

## 配置结果

- 根 `AGENTS.md` 包含唯一的 `## Agent skills` 配置块。
- `docs/agents/issue-tracker.md` 记录 GitHub Issues 操作约定。
- `docs/agents/triage-labels.md` 记录默认标签映射。
- `docs/agents/domain.md` 记录 multi-context 消费规则。
- `CONTEXT-MAP.md` 与各 `CONTEXT.md` 不预先创建，由 `domain-modeling` 在术语或决策实际确认后按需生成。

## 验证结果

- `git diff --check`：通过。
- `make lint`：通过（使用仓库内置 `.tools/make/tools/install/bin/make.exe`）。
- `make typecheck`：通过，mypy 检查 124 个源文件无问题，Vue/Nuxt/TypeScript 检查通过。
- `make test`：通过，Python 989 项通过、25 项按既有条件跳过；UI 53 项、Web 92 项通过。
- `make contract-test`：通过，生成结果可复现，契约测试 79 项通过。
- `make security-check`：通过，Python 与生产 Node 依赖未发现已知漏洞，Trivy 未发现高危或严重 secret/misconfiguration 问题。
- Git remote：通过，`origin` 的 fetch/push 均为 `https://github.com/flyingTurkey/codex.git`。
- GitHub CLI：通过，使用 `D:\devtools\githubcli\gh.exe` 2.96.0，`gh auth status` 确认当前活动账号为 `flyingTurkey`。
- GitHub triage 标签：通过；`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix` 均在 `flyingTurkey/codex` 中恰好存在一次。仅补充四个缺失标签，未修改既有 `wontfix`，也未向任何 Issue 或 Project 应用标签。

## 结论

仓库级 `setup-matt-pocock-skills` 配置、质量门禁、GitHub CLI 认证与默认 triage 标签均已通过验证，GitHub Issues 工程工作流已具备运行条件。
