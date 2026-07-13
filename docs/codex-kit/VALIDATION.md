# 交付校验记录

校验日期：2026-07-13  
版本：`v1.1.0-avocado-ui`

本开发包是可直接交给 Codex 分轮实施的产品、架构、UI与素材基线，不是已经完成的业务系统。

## 已通过

- 排除 `node_modules` 与构建产物后，21/21 个 JSON 文件可解析；
- 12/12 个 Draft 2020 JSON Schema 在 AJV strict 模式下编译通过；其中有外部 `$ref` 的 Schema 使用对应依赖 Schema 一并编译；
- `sample_items.json` 通过既有统一内容只读模型校验；
- `assets/ui/contracts/feed-page.example.json` 通过新增 `feed-page.schema.json` 校验；
- `assets/ui/fixtures/feed-story-fixtures.json` 通过 `feed-story-fixtures.schema.json` 校验，覆盖八种内容类型和 R3 受限、撤回状态；
- 4/4 个原有示例的 Claim 与 Evidence 双向引用完整，ID 唯一；
- `taxonomy.yaml` 保持原校验通过状态；
- 5 个 CSV 可解析；来源注册表含 42 个候选来源，全部为 `CANDIDATE` 且 `enabled=false`；
- 3 张 UI 参考 PNG 可读取：AIHOT 信息流 2048×1152、AIHOT 内容页 2048×894、方案1视觉稿 1487×1058；
- 文档中识别出的 58 个 `docs/codex-kit/...` 本地路径全部存在；
- `prototype/selected-feed` 执行 `npm run build` 成功，产出 Vite 生产构建；
- 原型正式依赖为 Vue 3、Vite 和 Iconoir，不引入 React；正式生产仍按 Nuxt 4 约束实施。

## 视觉 QA 状态

选中视觉稿可以打开，原型生产构建通过，但本次可用浏览器的安全策略拒绝打开本地预览地址，因此无法取得浏览器渲染截图、控制台记录和同视口对比。

`prototype/selected-feed/design-qa.md` 已将结果标记为 `blocked`，并列出第00A轮必须完成的浏览器视觉回归、交互与axe检查。不得把“构建通过”描述为“视觉验收通过”。

## 有意跳过

未把示例摘录哈希复算作为交付门禁。哈希不影响 Markdown、CSV、YAML、JSON、PNG 或原型素材打开，也不阻塞 Codex 初始化和前后端联调。真实采集与正式发布阶段应由服务端自动计算并核验 SHA-256。

## 使用边界

- 42 个来源是待准入候选种子，不代表已完成 robots、条款、版权、访问频率和解析稳定性审批；
- 示例与 UI Story 全部标记为演示且不可发布；
- AIHOT 截图和方案图只用于内部设计参考，不得复制其 Logo、品牌或作为生产背景；
- 正式四川路桥 Logo、字体和品牌色仍须品牌管理部门确认；
- 未经真实来源连续运行、金标评测、安全测试、视觉/无障碍验收和恢复演练，不得宣称系统达到生产就绪。

