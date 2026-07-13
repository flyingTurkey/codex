<script setup lang="ts">
import type { VersionResponse } from '@srbg/contracts'

defineProps<{
  apiReachable: boolean
  version: VersionResponse | null
}>()

const metrics = [
  { label: '今日新增', tone: 'digital' },
  { label: '精选', tone: 'verified' },
  { label: '待审核', tone: 'regulation' },
  { label: '异常来源', tone: 'case' },
] as const
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="topbar__content">
        <a class="brand" href="/" aria-label="四川路桥·智安情报首页">
          <span class="brand__name">四川路桥·智安情报</span>
        </a>
        <div class="topbar__meta">
          <span class="environment-label">演示环境</span>
          <span class="update-label">数据更新时间：尚无业务数据</span>
        </div>
      </div>
    </header>

    <main class="dashboard" aria-labelledby="page-title">
      <section class="dashboard__heading">
        <div>
          <h1 id="page-title">今日情报概览</h1>
          <p>工程基线已就绪，业务内容将在后续纵向切片接入。</p>
        </div>
        <p
          class="connection-status"
          :class="apiReachable ? 'connection-status--ready' : 'connection-status--degraded'"
          role="status"
        >
          <template v-if="apiReachable && version">
            API {{ version.api_version }} · Schema {{ version.content_schema_version }}
          </template>
          <template v-else>服务连接暂不可用</template>
        </p>
      </section>

      <section class="metrics" aria-label="今日指标">
        <article
          v-for="metric in metrics"
          :key="metric.label"
          class="metric"
          :class="`metric--${metric.tone}`"
          data-testid="metric"
        >
          <p class="metric__label">{{ metric.label }}</p>
          <p class="metric__value" data-testid="metric-value">--</p>
          <p class="metric__note">暂无业务数据</p>
        </article>
      </section>

      <section class="channels" aria-label="情报频道">
        <article class="channel channel--digital">
          <div class="channel__heading">
            <h2>数字化精选</h2>
            <span>数字化与科技创新</span>
          </div>
          <div class="empty-state">
            <span class="empty-state__marker" aria-hidden="true" />
            <div>
              <p>暂无业务数据</p>
              <span>案例、论文、软件与设备将在后续轮次接入。</span>
            </div>
          </div>
        </article>

        <article class="channel channel--safety">
          <div class="channel__heading">
            <h2>安全重点</h2>
            <span>安全规定与案例</span>
          </div>
          <div class="empty-state">
            <span class="empty-state__marker" aria-hidden="true" />
            <div>
              <p>暂无业务数据</p>
              <span>安全规定与官方案例将在审核能力就绪后接入。</span>
            </div>
          </div>
        </article>
      </section>
    </main>
  </div>
</template>
