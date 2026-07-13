# UI 06｜交互原型说明

路径：`prototype/selected-feed/`

## 用途

该原型用于：

- 对齐方案 1 的布局、密度、颜色和组件关系；
- 演示搜索、类型 Tab、复核筛选、收藏、空态和证据抽屉；
- 为 Codex/前端开发提供视觉回归基准。

它不是生产应用，不包含真实 API、SSO、权限、发布门禁或数据持久化。正式实现必须使用现有 Nuxt 4 monorepo，并以服务端契约和权限为准。

## 本地运行

```bash
cd docs/codex-kit/prototype/selected-feed
npm ci
npm run dev -- --host 0.0.0.0
```

构建：

```bash
npm run build
```

## 视觉真相优先级

1. `assets/ui/references/selected-concept-01.png`；
2. `assets/ui/design_tokens.json`；
3. `docs/ui/01-design-system.md`；
4. 原型实现。

如果原型与 Token/规范冲突，正式项目以 Token 和规范为准，并更新视觉回归截图。

