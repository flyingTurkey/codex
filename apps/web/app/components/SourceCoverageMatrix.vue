<script setup lang="ts">
import { EmptyState, StatusBadge } from '@srbg/ui'

import type { SourceCoverageCell } from '../source-center'

defineProps<{
  cells: readonly SourceCoverageCell[]
}>()

const industryLabels: Readonly<Record<string, string>> = {
  BRIDGE: '桥梁',
  GENERAL_TRANSPORT: '综合交通',
  HIGHWAY: '公路',
  RAILWAY: '铁路',
  RAIL_TRANSIT: '轨道交通',
  TUNNEL: '隧道',
  UNKNOWN: '未知行业',
}
const contentDomainLabels: Readonly<Record<string, string>> = {
  ACCIDENT_INVESTIGATION: '事故调查',
  AI_APPLICATION: 'AI 应用',
  DIGITAL_TRANSFORMATION_CASE: '数字化案例',
  IOT_EQUIPMENT: '物联网设备',
  LOW_ALTITUDE_EQUIPMENT: '低空设备',
  OFFICIAL_NOTICE: '官方通报',
  PENALTY: '处罚',
  RECTIFICATION: '整改',
  RESEARCH_PAPER: '论文',
  SAFETY_REGULATION: '安全规定',
  SOFTWARE_PLATFORM: '软件 / 平台',
  STANDARD_GUIDANCE: '标准 / 指南',
  UNKNOWN: '未知内容域',
}
const sourceTypeLabels: Readonly<Record<string, string>> = {
  academic_api: '学术 API',
  academic_database: '学术数据库',
  association: '协会',
  enterprise: '企业',
  government: '政府',
  journal: '期刊',
  media: '媒体',
  research_institute: '研究机构',
  standards: '标准机构',
}

function displayLabel(labels: Readonly<Record<string, string>>, value: string): string {
  return labels[value] ?? value
}
</script>

<template>
  <div v-if="cells.length" class="coverage-table-scroll" tabindex="0" role="region" aria-label="可滚动来源覆盖矩阵">
    <table aria-label="来源覆盖矩阵">
      <thead>
        <tr>
          <th scope="col">工程行业</th>
          <th scope="col">内容域</th>
          <th scope="col">来源类型</th>
          <th scope="col">地区 / 语言</th>
          <th scope="col">候选</th>
          <th scope="col">试运行</th>
          <th scope="col">ACTIVE</th>
          <th scope="col">覆盖结论</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="cell in cells" :key="`${cell.industry}:${cell.content_domain}:${cell.source_type}:${cell.region}:${cell.language}`">
          <th scope="row">{{ displayLabel(industryLabels, cell.industry) }}</th>
          <td>{{ displayLabel(contentDomainLabels, cell.content_domain) }}</td>
          <td>{{ displayLabel(sourceTypeLabels, cell.source_type) }}</td>
          <td>{{ cell.region }} / {{ cell.language }}</td>
          <td>{{ cell.candidate_count }}</td>
          <td>{{ cell.trial_count }}</td>
          <td>{{ cell.active_count }}</td>
          <td>
            <StatusBadge
              :tone="cell.gap ? 'conflict' : 'healthy'"
              :label="cell.gap ? '缺口' : '已有生产覆盖'"
            />
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <EmptyState
    v-else
    title="暂无覆盖单元"
    description="缺失的分类维度应保持 UNKNOWN；系统不会用网址数量替代覆盖质量。"
    icon="Reports"
  />
</template>

<style scoped>
.coverage-table-scroll {
  max-width: 100%;
  overflow-x: auto;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.coverage-table-scroll:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}

table {
  width: 100%;
  min-width: 62rem;
  border-collapse: collapse;
}

th,
td {
  padding: var(--spacing-3) var(--spacing-4);
  color: var(--color-ink-700);
  text-align: left;
  vertical-align: middle;
  border-bottom: 1px solid var(--color-border);
}

thead th {
  color: var(--color-ink-900);
  background: var(--color-surfaceMuted);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
  white-space: nowrap;
}

tbody th {
  color: var(--color-ink-900);
  font-weight: var(--font-weight-semibold);
}

tbody tr:last-child th,
tbody tr:last-child td {
  border-bottom: 0;
}
</style>
