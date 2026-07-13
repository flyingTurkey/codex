# 第 00 轮：工程基线（可直接复制给 Codex）

```text
执行第00轮：建立四川路桥行业数智与安全情报平台的可运行工程基线。

先阅读：
- AGENTS.md
- docs/codex-kit/README.md
- docs/codex-kit/docs/03-technical-architecture.md
- docs/codex-kit/docs/07-slo-test-acceptance.md
- docs/codex-kit/assets/ui/design_tokens.json

本轮目标：
在空仓库中建立 monorepo，使开发者通过一条命令启动 Nuxt Web、FastAPI API、Celery Worker、PostgreSQL、Redis 和 MinIO；建立 CI、测试、配置、日志、健康检查和最小首页骨架。

必须交付：
1. apps/web：Node.js 24 LTS + Nuxt 4 + Vue 3 + TypeScript strict + Nuxt UI 4；
2. apps/api：Python 3.12 + FastAPI + Pydantic 2 + SQLAlchemy 2 + Alembic；
3. apps/worker：共享后端领域代码的 Celery Worker；
4. packages/contracts：首期枚举、Problem Details、分页和健康契约；
5. infra/compose：PostgreSQL 17、Redis 7、MinIO，不使用 latest 镜像；
6. Makefile：setup、dev、down、lint、typecheck、test、contract-test、security-check；
7. .env.example：只含安全示例值和注释；
8. /health/live、/health/ready、/api/v1/version；
9. 首页开发骨架，采用设计令牌并显示“演示环境”；
10. Ruff、mypy strict、pytest、ESLint、TypeScript、Vitest、Playwright 基线；
11. CI：安装、lint、typecheck、单元测试、契约测试、依赖和密钥扫描；
12. CHANGELOG.md、docs/adr/0001-modular-monolith.md 和开发启动说明。

强制约束：
- 不实现真实业务模块；
- 不接入真实模型和真实SSO，使用 Mock；
- 不引入微服务、Kafka、Kubernetes、OpenSearch、图数据库；
- 依赖解析后锁定确切版本并提交 lockfile；
- 所有外部I/O都有超时；
- 时间UTC存储，界面Asia/Shanghai展示。

测试驱动：
- 先写健康接口、版本接口、前端首页和 Worker 健康测试并观察失败；
- 再做最小实现；
- Docker健康检查、API契约和首页端到端测试必须进入CI。

验收：
1. 新环境执行 make setup && make dev 后全部服务健康；
2. curl /health/ready 返回数据库、Redis、对象存储依赖状态；
3. curl /api/v1/version 返回 api_version 和 content_schema_version；
4. 首页可访问、无控制台错误，并通过基本无障碍扫描；
5. make lint typecheck test contract-test security-check 全部通过；
6. 停止 Redis 后 readiness 失败但 liveness 保持成功；
7. 不存在提交到Git的密钥、浮动latest镜像和跳过测试。

结束时提交代码，提供变更、命令真实输出、已知限制、提交哈希和下一轮是否可开始。
```
