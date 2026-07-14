<script setup lang="ts">
import type { ItemDetail } from '@srbg/contracts'
import { PageHeader } from '@srbg/ui'
import { ref } from 'vue'

import EvidenceDrawer from '../../components/EvidenceDrawer.vue'
import IntelligenceCard from '../../components/IntelligenceCard.vue'

const route = useRoute()
const itemId = String(route.params.id)
const { data: detail, status, error } = await useFetch<ItemDetail>(`/api/v1/items/${itemId}`, {
  retry: 0,
  timeout: 5_000,
})
const evidenceOpen = ref(false)
</script>

<template>
  <section class="item-detail-page">
    <PageHeader
      title="安全规定详情"
      eyebrow="字段与证据"
      description="待审核内容由服务端限制投影；发布后才显示审核通过的字段与段落证据。"
    />

    <p v-if="status === 'pending'" role="status">正在加载详情…</p>
    <p v-else-if="error" role="alert">详情暂时不可用。</p>
    <template v-else-if="detail">
      <div v-if="detail.notice" class="item-detail-page__notice" role="status">
        {{ detail.notice.message }}
      </div>
      <IntelligenceCard :item="detail.item" @evidence="evidenceOpen = true" />

      <section v-if="detail.claims?.length" class="item-detail-page__claims">
        <h2>已接受字段</h2>
        <dl>
          <div v-for="claim in detail.claims" :key="claim.id">
            <dt>{{ claim.label }}</dt>
            <dd>{{ claim.value }}</dd>
          </div>
        </dl>
        <button type="button" @click="evidenceOpen = true">
          查看 {{ detail.evidence?.length ?? 0 }} 条字段证据
        </button>
      </section>
    </template>

    <EvidenceDrawer
      :open="evidenceOpen"
      :item-id="itemId"
      :claims="detail?.claims ?? []"
      :evidence="detail?.evidence ?? []"
      @close="evidenceOpen = false"
    />
  </section>
</template>

<style scoped>
.item-detail-page {
  display: grid;
  width: min(100%, var(--srbg-layout-content-max));
  margin-inline: auto;
  gap: var(--spacing-5);
}

.item-detail-page__notice {
  padding: var(--spacing-3) var(--spacing-4);
  color: var(--color-ink-700);
  background: var(--color-reviewPending-50);
  border: 1px solid var(--color-reviewPending-300);
  border-radius: var(--radius-sm);
}

.item-detail-page__claims {
  padding: var(--spacing-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.item-detail-page__claims h2 {
  margin-top: 0;
}

.item-detail-page__claims dl {
  display: grid;
  gap: var(--spacing-3);
}

.item-detail-page__claims dt {
  color: var(--color-ink-500);
  font-size: var(--text-xs);
}

.item-detail-page__claims dd {
  margin: var(--spacing-1) 0 0;
}

.item-detail-page__claims button {
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-surface);
  background: var(--color-brand-700);
  border: 0;
  border-radius: var(--radius-sm);
}
</style>
