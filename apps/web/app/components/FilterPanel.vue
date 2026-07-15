<script setup lang="ts">
import type {
  FeedContentTypeFilter,
  FeedContentTypeOption,
} from '../composables/useIntelligenceFeed'

withDefaults(
  defineProps<{
    domain?: 'all' | 'safety' | 'digital'
    contentType?: FeedContentTypeFilter
    contentTypeOptions?: readonly FeedContentTypeOption[]
    showDomain?: boolean
    showDigitalFilters?: boolean
    showPaperFilters?: boolean
    showProductFilters?: boolean
    engineeringDomain?: string
    scenario?: string
    maturity?: string
    sourceNature?: string
    paperType?: string
    technologyTag?: string
    accessLevel?: string
    publicationYear?: string
    productKind?: string
    evidenceLevel?: string
    deploymentMode?: string
  }>(),
  {
    domain: 'all',
    contentType: 'all',
    contentTypeOptions: () => [
      { label: '全部类型', value: 'all' },
      { label: '安全规定', value: 'SAFETY_REGULATION' },
    ],
    showDomain: true,
    showDigitalFilters: false,
    showPaperFilters: false,
    showProductFilters: false,
    engineeringDomain: 'all',
    scenario: 'all',
    maturity: 'all',
    sourceNature: 'all',
    paperType: 'all',
    technologyTag: 'all',
    accessLevel: 'all',
    publicationYear: 'all',
    productKind: 'all',
    evidenceLevel: 'all',
    deploymentMode: 'all',
  },
)

const emit = defineEmits<{
  'update:domain': [value: 'all' | 'safety' | 'digital']
  'update:contentType': [value: FeedContentTypeFilter]
  'update:engineeringDomain': [value: string]
  'update:scenario': [value: string]
  'update:maturity': [value: string]
  'update:sourceNature': [value: string]
  'update:paperType': [value: string]
  'update:technologyTag': [value: string]
  'update:accessLevel': [value: string]
  'update:publicationYear': [value: string]
  'update:productKind': [value: string]
  'update:evidenceLevel': [value: string]
  'update:deploymentMode': [value: string]
}>()
</script>

<template>
  <form class="filter-panel" aria-label="情报筛选" @submit.prevent>
    <label v-if="showDomain">
      频道
      <select
        :value="domain"
        @change="emit('update:domain', ($event.target as HTMLSelectElement).value as 'all' | 'safety' | 'digital')"
      >
        <option value="all">全部</option>
        <option value="safety">安全</option>
        <option value="digital">数字化</option>
      </select>
    </label>
    <fieldset class="filter-panel__types" role="group" aria-label="安全内容类型">
      <legend>内容类型</legend>
      <div class="filter-panel__segments">
        <button
          v-for="option in contentTypeOptions"
          :key="option.value"
          type="button"
          :data-content-type="option.value"
          :aria-pressed="contentType === option.value"
          @click="emit('update:contentType', option.value)"
        >
          {{ option.label }}
        </button>
      </div>
    </fieldset>
    <template v-if="showDigitalFilters || showPaperFilters || showProductFilters">
      <label>
        工程专业
        <select
          aria-label="工程专业"
          :value="engineeringDomain"
          @change="emit('update:engineeringDomain', ($event.target as HTMLSelectElement).value)"
        >
          <option value="all">全部专业</option>
          <option value="HIGHWAY">公路</option>
          <option value="BRIDGE">桥梁</option>
          <option value="TUNNEL">隧道</option>
          <option value="ROAD">道路</option>
          <option value="GENERAL_CONSTRUCTION">工程施工</option>
        </select>
      </label>
      <label v-if="showDigitalFilters || showProductFilters">
        应用场景
        <select
          aria-label="应用场景"
          :value="scenario"
          @change="emit('update:scenario', ($event.target as HTMLSelectElement).value)"
        >
          <option value="all">全部场景</option>
          <option value="QUALITY_CONTROL">质量控制</option>
          <option value="PROGRESS_CONTROL">进度控制</option>
          <option value="INSPECTION">巡检</option>
          <option value="STRUCTURAL_HEALTH_MONITORING">结构健康监测</option>
          <option value="DECISION_SUPPORT">决策支持</option>
        </select>
      </label>
      <label>
        成熟度
        <select
          aria-label="成熟度"
          :value="maturity"
          @change="emit('update:maturity', ($event.target as HTMLSelectElement).value)"
        >
          <option value="all">全部成熟度</option>
          <option value="CONCEPT">概念</option>
          <option value="LAB_PROTOTYPE">实验室原型</option>
          <option value="ENGINEERING_PROTOTYPE">工程样机</option>
          <option value="PILOT">试点</option>
          <option value="SINGLE_PROJECT_PRODUCTION">单项目生产应用</option>
          <option value="MULTI_PROJECT_REPLICATION">多项目复制</option>
          <option value="ENTERPRISE_SCALE">企业规模应用</option>
          <option value="UNKNOWN">成熟度未知</option>
        </select>
      </label>
      <template v-if="showProductFilters">
        <label>
          产品类型
          <select
            aria-label="产品类型"
            :value="productKind"
            @change="emit('update:productKind', ($event.target as HTMLSelectElement).value)"
          >
            <option value="all">全部产品类型</option>
            <option value="PROJECT_MANAGEMENT_PLATFORM">项目管理平台</option>
            <option value="MONITORING_TERMINAL">监测终端</option>
            <option value="UAV_DOCK">无人机/机场</option>
            <option value="INSPECTION_ROBOT">巡检机器人</option>
          </select>
        </label>
        <label>
          证据等级
          <select
            aria-label="证据等级"
            :value="evidenceLevel"
            @change="emit('update:evidenceLevel', ($event.target as HTMLSelectElement).value)"
          >
            <option value="all">全部证据等级</option>
            <option value="VENDOR_CLAIM_ONLY">仅厂商声明</option>
            <option value="PROJECT_EVIDENCE">工程案例证据</option>
            <option value="RESEARCH_EVIDENCE">研究证据</option>
            <option value="INDEPENDENT_VALIDATION">独立验证</option>
            <option value="OFFICIAL_CERTIFICATION">官方许可或认证</option>
            <option value="UNKNOWN">证据等级未知</option>
          </select>
        </label>
        <label>
          部署方式
          <select
            aria-label="部署方式"
            :value="deploymentMode"
            @change="emit('update:deploymentMode', ($event.target as HTMLSelectElement).value)"
          >
            <option value="all">全部部署方式</option>
            <option value="SAAS">SaaS</option>
            <option value="PRIVATE_DEPLOYMENT">私有化部署</option>
            <option value="EDGE">边缘部署</option>
            <option value="ON_DEVICE">设备端</option>
          </select>
        </label>
      </template>
      <label v-if="showDigitalFilters">
        来源性质
        <select
          aria-label="来源性质"
          :value="sourceNature"
          @change="emit('update:sourceNature', ($event.target as HTMLSelectElement).value)"
        >
          <option value="all">全部来源</option>
          <option value="GOVERNMENT_CASE_COLLECTION">政府典型案例</option>
          <option value="ENTERPRISE_SELF_REPORT">企业自述</option>
        </select>
      </label>
      <template v-if="showPaperFilters">
        <label>
          论文类型
          <select
            aria-label="论文类型"
            :value="paperType"
            @change="emit('update:paperType', ($event.target as HTMLSelectElement).value)"
          >
            <option value="all">全部类型</option>
            <option value="ARTICLE">研究论文</option>
            <option value="REVIEW">综述</option>
            <option value="METHOD">方法论文</option>
            <option value="CASE_STUDY">案例研究</option>
            <option value="OTHER">其他</option>
          </select>
        </label>
        <label>
          技术标签
          <select
            aria-label="技术标签"
            :value="technologyTag"
            @change="emit('update:technologyTag', ($event.target as HTMLSelectElement).value)"
          >
            <option value="all">全部技术</option>
            <option value="DIGITAL_TWIN">数字孪生</option>
            <option value="SENSOR_NETWORK">传感网络</option>
            <option value="COMPUTER_VISION">计算机视觉</option>
            <option value="MACHINE_LEARNING">机器学习</option>
            <option value="UAV">无人机</option>
          </select>
        </label>
        <label>
          开放状态
          <select
            aria-label="开放状态"
            :value="accessLevel"
            @change="emit('update:accessLevel', ($event.target as HTMLSelectElement).value)"
          >
            <option value="all">全部状态</option>
            <option value="METADATA_ONLY">仅题录</option>
            <option value="ABSTRACT_ALLOWED">摘要可展示</option>
            <option value="OPEN_FULLTEXT">开放全文入口</option>
          </select>
        </label>
        <label>
          发表年份
          <select
            aria-label="发表年份"
            :value="publicationYear"
            @change="emit('update:publicationYear', ($event.target as HTMLSelectElement).value)"
          >
            <option value="all">全部年份</option>
            <option v-for="year in [2026, 2025, 2024, 2023, 2022]" :key="year" :value="year">
              {{ year }}
            </option>
          </select>
        </label>
      </template>
    </template>
  </form>
</template>

<style scoped>
.filter-panel {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.filter-panel label {
  display: grid;
  min-width: 10rem;
  color: var(--color-ink-600);
  font-size: var(--text-xs);
  gap: var(--spacing-1);
}

.filter-panel__types {
  display: grid;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
  gap: var(--spacing-1);
}

.filter-panel__types legend {
  padding: 0;
  color: var(--color-ink-600);
  font-size: var(--text-xs);
}

.filter-panel__segments {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1);
}

.filter-panel__segments button {
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-4);
  color: var(--color-ink-700);
  font: inherit;
  font-weight: var(--font-weight-semibold);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.filter-panel__segments button[aria-pressed='true'] {
  color: var(--color-surface);
  background: var(--color-brand-700);
  border-color: var(--color-brand-700);
}

.filter-panel select {
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-ink-800);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

@media (max-width: 39.999rem) {
  .filter-panel,
  .filter-panel label,
  .filter-panel__types {
    width: 100%;
  }

  .filter-panel__segments button {
    flex: 1 1 0;
  }
}
</style>
