# 方案 1 交互原型

这是“四川路桥·智安情报”低饱和牛油果时间线信息流的视觉与交互参考。

实现：Vue 3 + Vite + Iconoir。它不是生产应用，不接入真实 API、权限、审核或发布门禁；正式开发仍使用项目约定的 Nuxt 4 monorepo。

已实现的原型交互：

- 内容类型 Tab；
- 关键词/来源/标签搜索；
- 仅看已人工复核；
- 收藏切换；
- 筛选无结果与一键恢复；
- 证据抽屉；
- 完整侧栏、紧凑侧栏和移动布局。

```bash
npm ci
npm run dev -- --host 0.0.0.0
npm run build
```

视觉真相：`../../assets/ui/references/selected-concept-01.png`。

