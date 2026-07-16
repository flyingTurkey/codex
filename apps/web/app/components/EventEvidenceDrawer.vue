<script setup lang="ts">
import type { PublishedClaimV1, PublishedEvidenceReferenceV1 } from '@srbg/contracts'
import { ResponsiveDrawer } from '@srbg/ui'
import { computed } from 'vue'

const props = defineProps<{
  open: boolean
  claims: readonly PublishedClaimV1[]
  evidence: readonly PublishedEvidenceReferenceV1[]
}>()
const emit = defineEmits<{ close: [] }>()

const model = computed({
  get: () => props.open,
  set: (value: boolean) => { if (!value) emit('close') },
})

function relatedClaims(evidenceId: string): readonly PublishedClaimV1[] {
  return props.claims.filter((claim) => claim.evidence_ids.includes(evidenceId))
}
</script>

<template>
  <ResponsiveDrawer
    v-model="model"
    title="原文段落与页码定位"
    description="仅展示服务端 Event 发布投影中的定位、内容哈希和关联事实。"
    close-label="关闭证据抽屉"
  >
    <section class="event-evidence-drawer" aria-labelledby="event-evidence-list-title">
      <h3 id="event-evidence-list-title">已发布证据引用</h3>
      <p class="event-evidence-drawer__notice">
        该视图不补全原文摘录或链接；定位与哈希用于核对已发布事实。
      </p>
      <ol v-if="evidence.length" class="event-evidence-drawer__list">
        <li v-for="entry in evidence" :key="entry.evidence_id">
          <dl>
            <div>
              <dt>证据定位</dt>
              <dd>{{ entry.locator }}</dd>
            </div>
            <div>
              <dt>SHA-256</dt>
              <dd><code>{{ entry.content_sha256 }}</code></dd>
            </div>
          </dl>
          <section :aria-label="`证据 ${entry.evidence_id} 关联的已发布事实`">
            <h4>关联已发布事实</h4>
            <ul v-if="relatedClaims(entry.evidence_id).length">
              <li v-for="claim in relatedClaims(entry.evidence_id)" :key="claim.claim_id">
                <strong>{{ claim.field_name }}</strong>
                <span>{{ claim.value }}</span>
              </li>
            </ul>
            <p v-else>当前发布投影未返回关联事实。</p>
          </section>
        </li>
      </ol>
      <p v-else role="status">当前发布投影未返回匹配的证据引用。</p>
    </section>
  </ResponsiveDrawer>
</template>

<style scoped>
.event-evidence-drawer,
.event-evidence-drawer__list,
.event-evidence-drawer__list > li,
.event-evidence-drawer__list dl,
.event-evidence-drawer__list section,
.event-evidence-drawer__list ul {
  display: grid;
  gap: var(--spacing-3);
}

.event-evidence-drawer h3,
.event-evidence-drawer h4,
.event-evidence-drawer p,
.event-evidence-drawer dl,
.event-evidence-drawer dd {
  margin: 0;
}

.event-evidence-drawer__notice {
  padding: var(--spacing-3);
  color: var(--color-ink-700);
  background: var(--color-brand-50);
  border-radius: var(--radius-sm);
}

.event-evidence-drawer__list {
  padding: 0;
  list-style: none;
}

.event-evidence-drawer__list > li {
  padding: var(--spacing-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.event-evidence-drawer__list dl > div {
  display: grid;
  grid-template-columns: minmax(6rem, 0.25fr) minmax(0, 1fr);
  gap: var(--spacing-3);
}

.event-evidence-drawer__list dt {
  color: var(--color-ink-600);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
}

.event-evidence-drawer__list dd,
.event-evidence-drawer__list code {
  overflow-wrap: anywhere;
}

.event-evidence-drawer__list ul {
  margin: 0;
  padding-left: var(--spacing-5);
}

.event-evidence-drawer__list ul li {
  display: grid;
  gap: var(--spacing-1);
}
</style>
