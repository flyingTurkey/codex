# 交付校验记录

> **LEGACY 副本**：本文只记录 2026-07-13 Codex 开发包的点时校验，统计和执行说明已不代表当前仓库。当前 kit 校验材料位于 `docs/codex-kit/VALIDATION.md`；项目状态与下一轮门禁见 `docs/operations/intelligence-v2-maintainer-guide.md`。

校验日期：2026-07-13

本开发包是可直接交给 Codex 分轮实施的设计与素材基线，不是已经编译好的业务系统。

## 已通过

- 15/15 个 JSON 文件可解析；
- 10/10 个 Draft 2020 JSON Schema 在 AJV strict 模式下编译通过；
- `sample_items.json` 通过统一内容只读模型校验；
- 4/4 个示例的 Claim 与 Evidence 双向引用完整，ID 唯一；
- `taxonomy.yaml` 可解析；
- 3 个 CSV 可解析，其中来源注册表含 42 个候选来源，全部为 `CANDIDATE` 且 `enabled=false`；
- 2 个 SVG 占位素材可作为 XML 解析；
- 文档中显式引用的 `docs/codex-kit/...` 本地路径全部存在。

## 有意跳过

未把示例摘录哈希复算作为交付门禁。哈希不影响 Markdown、CSV、YAML、JSON 或 SVG 素材的打开，也不阻塞 Codex 初始化和前后端联调。真实采集与正式发布阶段应由服务端自动计算并核验 SHA-256。

## 使用边界

- 42 个来源是待准入的候选种子，不代表已完成 robots、条款、版权、访问频率和解析稳定性审批；
- 示例条目全部标记为演示且不可发布；
- 未经真实来源连续运行、金标评测、安全测试和恢复演练，不得宣称系统达到生产就绪。
