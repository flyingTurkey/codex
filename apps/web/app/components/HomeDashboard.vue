<script setup lang="ts">
import type { ProblemDetails, VersionResponse } from '@srbg/contracts'
import { ProblemNotice } from '@srbg/ui'
import { computed } from 'vue'

import IntelligenceFeedPage from './IntelligenceFeedPage.vue'

const props = defineProps<{
  problem: ProblemDetails | null
  version: VersionResponse | null
}>()

const baselineAvailable = computed(() => props.problem === null && props.version !== null)
</script>

<template>
  <IntelligenceFeedPage
    title="今日精选"
    eyebrow="行业情报工作台"
    description="当前仅展示可验证的工程基线；业务内容将在后续纵向切片接入。"
    :status-label="baselineAvailable ? '工程基线可用' : undefined"
    status-tone="healthy"
    empty-title="业务数据尚未接入"
    empty-description="后续轮次将接入经过来源、证据和发布门禁处理的真实业务数据。"
  >
    <template v-if="baselineAvailable && version" #status-detail>
      <span>API {{ version.api_version }} · Schema {{ version.content_schema_version }}</span>
    </template>

    <template v-if="problem" #notice>
      <ProblemNotice :problem="problem" />
    </template>
  </IntelligenceFeedPage>
</template>
