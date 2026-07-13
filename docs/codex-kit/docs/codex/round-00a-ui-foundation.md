# 第 00A 轮：方案 1 设计系统与应用壳层（可直接复制给 Codex）

```text
执行第00A轮：在已经完成第00轮工程基线的仓库中，落地“AIHOT式高密度时间线 + 低饱和牛油果主题”的设计系统与应用壳层。

开始前必须：
1. 完整阅读根目录 AGENTS.md；
2. 阅读 docs/codex-kit/README.md；
3. 阅读 docs/codex-kit/docs/06-ui-ux-spec.md 和 docs/codex-kit/docs/ui/全部文件；
4. 阅读 docs/codex-kit/assets/ui/design_tokens.json、component_inventory.csv、page_state_matrix.csv；
5. 打开 docs/codex-kit/assets/ui/references/selected-concept-01.png 作为视觉真相；
6. 检查 git status、现有 apps/web、packages/ui、测试、lockfile 和第00轮验收记录；
7. 先实际重跑第00轮关键门禁。失败时只修复第00轮，不开始本轮；
8. 复述本轮范围、现有代码复用点、实施步骤、验收命令和明确不做项。

背景：第00轮已经执行。本轮不得重新脚手架、替换框架、覆盖现有首页或丢弃用户已有修改。发现实际仓库与开发包假设不一致时，先报告差异并在现有结构上最小适配。

本轮用户价值：
用户打开平台即可看到统一的“四川路桥·智安情报”应用壳层、导航、页面头和真实空态；后续每一轮都能在同一套视觉、组件和响应式基线上增量开发，不再重复造页面。

必须交付：
1. 将 design_tokens.json 映射为 packages/ui 的类型安全 Token 和 Tailwind/Nuxt UI Theme；页面不得散落十六进制颜色；
2. 正式项目仍使用 Nuxt 4、Vue 3、TypeScript strict、Tailwind CSS、Nuxt UI 4，不引入 React 或第二套全量组件库；
3. 使用 Iconoir 图标，建立单一图标封装；正式四川路桥Logo未提供前使用文字锁定稿，不手绘或生成仿冒Logo；
4. 在 packages/ui 建立 AppShell、AppSidebar、PageHeader、StatusBadge、EmptyState、Skeleton、ProblemNotice、ResponsiveDrawer、FocusTrap 等基础原语；
5. 在 apps/web 接入应用壳层，建立今日精选、全部动态、数字化、安全情报、行业日报、收藏和按权限显示的管理入口；
6. 根路由只展示可验证的工程基线信息和真实空态，不硬编码看似真实的业务新闻；可增加仅开发环境可见的 /__ui-stories 页面读取 feed-story-fixtures.json；
7. 实现完整侧栏、1024px紧凑栏、768px抽屉导航和阅读页移动基线；
8. 状态必须由文字、图标和颜色共同表达，品牌绿不得替代事故/撤回/冲突语义色；
9. 实现跳过链接、键盘导航、清晰焦点、reduced-motion、200%缩放和WCAG AA基线；
10. 为每个基础组件建立 Vitest/Vue Test Utils 测试或项目既有等价测试；
11. 增加 Playwright：导航当前态、键盘、响应式侧栏/抽屉、开发空态；增加 axe 扫描；
12. 建立视觉回归基线，至少覆盖 1920×1080、1440×900、1024×768；不得把用户截图作为页面背景；
13. 更新 CHANGELOG.md、本轮验收记录和组件清单实现状态。

测试驱动顺序：
1. 先写 Token 映射、基础组件和应用壳层失败测试；
2. 最小实现设计系统；
3. 接入真实应用壳层和空态；
4. 补响应式、键盘和无障碍；
5. 运行视觉回归并修复P0/P1/P2差异；
6. 运行全局回归。

不得做：
- 不改数据库、业务API、采集、AI、审核或发布逻辑；
- 不实现看似完整但无真实后端的业务页面；
- 不创建第二套 Feed/Card；
- 不复制AIHOT Logo、名称或品牌图形；
- 不引入大Hero、霓虹、渐变、玻璃拟态或装饰新闻图；
- 不把原型目录作为生产依赖；
- 不删除第00轮已有实现来“重做得更整洁”。

验收：
1. 现有第00轮健康接口、Worker和开发启动流程不退化；
2. 主页壳层在1920、1440、1024和768宽度下无关键控件溢出；
3. 全键盘可进入导航、主内容和移动抽屉；
4. axe无critical/serious；
5. Token、组件和页面中没有第二套相冲突的品牌色硬编码；
6. 未实现业务显示真实空态，不显示伪造发布内容；
7. make lint typecheck test contract-test security-check web-e2e web-a11y 全部通过。

结束时提交代码，并提供：用户价值、变更文件、视觉截图、断点截图、测试真实输出、已知限制、提交哈希和是否满足第01轮门禁。
```

