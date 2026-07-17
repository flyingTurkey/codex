# PERS-05 验收记录：自动发现与自动启用

## 范围结论

本轮将个人产品的来源路径改为“免费发现优先 → 安全探测 → 自动建档/画像 → 固定规则评分 → 每日额度内自动启用”。旧候选表、后台 API 和兼容页面没有删除，但 `/sources` 与正常个人导航不再提供候选审批入口。本轮没有实现 Claim 自动接受，也没有改变 `PublicationService` 发布门禁。

## 数据与事务边界

- 迁移头为 `0025_personal_source_discovery`，前驱固定为 `0024_automatic_source_profiles`。
- 迁移预置 7 个主题，只为已有来源写入有界评分任务；迁移不创建网络客户端、不联网、不批量启用。
- `discovery_occurrence` 以主题、origin 哈希、渠道和父来源幂等累计；深度约束为 0/1。
- 探测和自动启用额度使用数据库原子函数，分别固定为上海自然日 100/20。
- 自动启用由 `auto_enable_personal_source` 在一个数据库事务内重新读取最新评分、sticky 状态、成功探测、连接器与样本事实，随后占用额度、激活来源/流/计划、写关键活动事件和 outbox。
- 有 PERS-05 业务事实时拒绝破坏性降级；无业务事实支持 `0024 → 0025 → 0024 → 0025` 回放。

## 评分和安全

规则版本固定为 `personal-source-auto-score-v1`，分项上限为 35/25/20/10/10，70 分含边界。权威和独立性没有进入评分输入。Owner 手工停用、SSRF、robots、访问障碍、连接器不可执行、无真实样本或证据过期均形成独立原因代码并阻止启用。DeepSeek 不可用时 PERS-04 的本地规则画像仍可形成评分；规则分达到 70 且所有硬门禁通过时可启用。

## 产品面

`/sources` 提供总开关、下次运行时间、主题编辑、今日探测/启用用量、百度状态、自动启用总分、五项分解、规则版本及未达标/硬门禁原因。百度 Key 不进入 API 响应。

## 验收命令

完成时记录以下命令的实际结果：

```text
make lint
make typecheck
make test
make contract-test
make security-check
make fixture-replay
make quality-gate
make personal-source-test
make web-e2e
make web-a11y
```

状态：通过。

- `quality-gate`：根级 1305 passed / 32 skipped，UI 53 passed，Web 116 passed，契约 108 passed；Ruff、mypy、Nuxt/Vue/TypeScript、依赖审计与 Trivy 高危/严重级扫描通过（pnpm 仅报告 1 个不阻断的 low）。
- `fixture-replay`：365 passed，离线评估通过，证据支持率与 Schema 通过率均为 10000 bps。
- `personal-source-test`：迁移正反回放通过，174 passed；个人来源 Web 116 passed。
- `web-e2e`：54 passed；`web-a11y`：17 passed，包含 `/sources` axe 检查。
