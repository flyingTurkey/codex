# PERS-10 旧企业治理退场验收

PERS-10 验收时迁移头为 `0030_pers10_role_archive_repair`；当前运行头随后扩展为 `0031_controlled_personal_runs`，仅增加个人真实试点的内部预算账本，不改变本页归档统计或恢复企业流程。`0029` 在单一 PostgreSQL 事务中归档旧治理记录；`0030` 保存 `srbg_admin_role`、`srbg_model_role`、`srbg_source_governance_writer` 三个角色的规范属性、成员关系和表授权，并修复已应用 0029 但未留下角色记录的数据库。归档 Schema 对 `PUBLIC` 及应用角色撤权，写操作由数据库触发器拒绝。

开发库实际归档 53 类、原始 69 行、归档 69 行；manifest 清单汇总 SHA-256 为 `780f6fd212970588e84d29f9fba169dc5ee5ef4903264cb46f9c831cbb75825c`。非零类别如下：

| 类别 | 数量 | 汇总 SHA-256 |
|---|---:|---|
| `database_role` | 3 | `a1e0a36ca4bdd7a0cacebb997bd26a19110d4672b6695cad7a0e4f12f9def1d4` |
| `review_task` | 60 | `0c50e44fdc561b47004da45a4cb94a7b02aa2eeb770b72ad28ff92fec4ca6468` |
| `round17_signed_approval` | 1 | `bac19769ca6c7b333ebfd9b80118e3cb04b4c735b4ee7031baf8a59ac46b8c9b` |
| `round17_staff_binding` | 1 | `b06f8d13a19979d29673efa5b80151942199819e313c3fee430e5cfe35ac388e` |
| `source_authority_assessment` | 1 | `d389febc967189dca8d651ac6eedcb3dcd5a2b3385b2951f2ae064e31d118cff` |
| `source_governance_metadata_audit` | 2 | `e02418ae4a48ed9dd710e411cb6a876e915c245b2dbbbf28d8da7b2ac05f1f34` |
| `source_independence_assessment` | 1 | `0b5a3bbe714c14e35b52eb0f26bc527a6f73c685a3682d5b9cf6da129d356210` |

迁移删除旧业务表、审核触发器、旧授权和企业数据库角色；代码删除旧 API、后台任务、生成契约、角色分支、页面组件及运行时模块。业务源代码不得读取归档 Schema。降级先重新计算并验证全部记录和 manifest；任何损坏以 `PERS10_ARCHIVE_CORRUPT` 或哈希错误中止，验证通过后才恢复原表、约束、触发器、授权、数据和 0029 前调度函数。

`make personal-migration-test` 使用独立 PostgreSQL 集群执行 `0028 → 0029 → 0030 → 损坏归档降级拒绝 → 0029 → 0028 → 0029 → 0030`，并模拟已应用 0029 且角色归档缺失的漂移状态。专项测试同时验证旧 API 不进入 OpenAPI、契约只保留 owner、业务代码不读取归档、旧审核触发器和旧角色正确退场。

固定评估结果：30 个来源、30 个内容；主题相关准确率 83.33%，健康原因命中率 100%，Evidence ID 有效率 100%，关键数字/日期无证据数 0，未验证 AI 进入事实索引数 0，人工审核任务新增数 0。

真实交通运输部采集、证据事实、PublicationService 投影、手工停用和受控原文变化失效证据见 [最终个人平台验收](final-personal-platform.md)。

## 最终门禁

- `make lint`、`make typecheck`：通过；Ruff、设计 Token、ESLint、mypy strict（122 个源文件）、Vue/Nuxt/TypeScript strict 全绿。
- `make test`：947 通过、25 跳过；UI 53/53、Web 单元 90/90。
- `make contract-test`：契约可重复生成，79/79 通过。
- `make security-check`：通过；pnpm 仅 1 个 low，Trivy Secret/Misconfiguration 无 HIGH/CRITICAL。
- `make fixture-replay`：350/350 通过；Round09 固定评估通过。
- `make quality-gate`：通过，并再次执行 lint、typecheck、test、contract-test、security-check。
- `make personal-source-test`：138/138 后端、90/90 Web，通过 `0024 → 0025 → 0024 → 0025`。
- `make personal-content-test`：58/58 后端、90/90 Web，通过 `0027 → 0028 → 0027 → 0028`。
- `make personal-migration-test`：17/17，通过独立 PostgreSQL 的 `0028 → 0029 → 0030 → 损坏降级拒绝 → 0029 → 0028 → 0029 → 0030` 及漂移修复；30+30 固定评估达标。
- `make web-e2e`：54/54；`make web-a11y`：17/17。
- 完整 `docker compose up --build --detach --wait`：全部服务健康；`make smoke` 验证 PostgreSQL、Redis、对象存储、API/Feed 通过。
- 旧管理 API 四个代表路径均为 HTTP 404；最终迁移头为 `0030_pers10_role_archive_repair`，三个退场角色剩余数为 0，应用角色归档 Schema USAGE 均为 false。
