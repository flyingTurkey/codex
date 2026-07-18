<script setup lang="ts">
import type {
  AutomaticRelationshipView,
  OwnerRelationshipCorrectionRequest,
  OwnerRelationshipCorrectionResponse,
} from '@srbg/contracts'
import { StatusBadge } from '@srbg/ui'
import { computed, ref } from 'vue'

import { createUuidV7 } from '../utils/uuid-v7'

const props = defineProps<{
  eventId: string
  relationships: readonly AutomaticRelationshipView[]
  itemIds: readonly string[]
}>()
const emit = defineEmits<{ refreshed: [] }>()

const reason = ref<Record<string, string>>({})
const splitReason = ref('')
const splitGroups = ref<Record<string, 'A' | 'B'>>({})
const busy = ref<string | null>(null)
const message = ref<string | null>(null)
const retryPayload = ref<OwnerRelationshipCorrectionRequest | null>(null)
const activeRelationships = computed(() => props.relationships.filter(row => row.status === 'ACTIVE'))

async function submit(payload: OwnerRelationshipCorrectionRequest): Promise<void> {
  busy.value = payload.command_id
  message.value = null
  try {
    await $fetch<OwnerRelationshipCorrectionResponse>(
      `/api/v1/events/${props.eventId}/relationship-corrections`,
      { method: 'POST', body: payload, retry: 0, timeout: 5_000 },
    )
    message.value = '个人纠正已保存，相关投影和缓存正在使用新版本。'
    retryPayload.value = null
    emit('refreshed')
  }
  catch {
    message.value = '纠正未保存，原关系保持不变。'
    retryPayload.value = payload
  }
  finally {
    busy.value = null
  }
}

function withdraw(row: AutomaticRelationshipView): void {
  const value = reason.value[row.id]?.trim()
  if (!value) return
  void submit({
    command_id: createUuidV7(),
    action: 'WITHDRAW_RELATION',
    reason: value,
    decision_id: row.id,
    member_item_ids: [],
    allocations: [],
    corrected_kind: null,
    corrected_source_item_id: null,
    corrected_target_item_id: null,
  })
}

function keepIndependent(row: AutomaticRelationshipView): void {
  const value = reason.value[row.id]?.trim()
  if (!value) return
  void submit({
    command_id: createUuidV7(),
    action: 'KEEP_INDEPENDENT',
    reason: value,
    decision_id: row.id,
    member_item_ids: [row.source_item_id, row.target_item_id],
    allocations: [],
    corrected_kind: null,
    corrected_source_item_id: null,
    corrected_target_item_id: null,
  })
}

function correctModel(row: AutomaticRelationshipView): void {
  const value = reason.value[row.id]?.trim()
  if (!value) return
  void submit({
    command_id: createUuidV7(),
    action: 'CORRECT_MODEL_RELATION',
    reason: value,
    decision_id: row.id,
    member_item_ids: [],
    allocations: [],
    corrected_kind: row.kind === 'MODEL_ALIAS' ? 'VERSION_SUCCESSOR' : 'MODEL_ALIAS',
    corrected_source_item_id: row.source_item_id,
    corrected_target_item_id: row.target_item_id,
  })
}

function splitEvent(): void {
  const value = splitReason.value.trim()
  if (!value || props.itemIds.length < 2) return
  const childA = createUuidV7()
  const childB = createUuidV7()
  const allocations = props.itemIds.map((itemId, index) => ({
    item_id: itemId,
    child_event_id: (splitGroups.value[itemId] ?? (index === 0 ? 'A' : 'B')) === 'A'
      ? childA
      : childB,
  }))
  if (new Set(allocations.map(row => row.child_event_id)).size < 2) {
    message.value = '拆分至少需要两个事件分组。'
    return
  }
  void submit({
    command_id: createUuidV7(),
    action: 'SPLIT_EVENT',
    reason: value,
    decision_id: null,
    member_item_ids: [],
    allocations,
    corrected_kind: null,
    corrected_source_item_id: null,
    corrected_target_item_id: null,
  })
}
</script>

<template>
  <section class="automatic-relationships" aria-labelledby="automatic-relationships-title">
    <header>
      <div>
        <h2 id="automatic-relationships-title">自动关系与个人纠正</h2>
        <p>算法关系不会删除原始记录；个人纠正优先于后续自动任务。</p>
      </div>
      <StatusBadge tone="info" label="可撤销自动关系" />
    </header>
    <p v-if="message" :role="retryPayload ? 'alert' : 'status'">
      {{ message }}
      <button v-if="retryPayload" type="button" :disabled="busy !== null" @click="submit(retryPayload)">重试</button>
    </p>
    <ol v-if="activeRelationships.length">
      <li v-for="row in activeRelationships" :key="row.id">
        <div>
          <strong>{{ row.kind }}</strong>
          <span>{{ (row.score_bps / 100).toFixed(2) }}% · {{ row.algorithm_version }}</span>
          <code>{{ row.source_item_id }} → {{ row.target_item_id }}</code>
          <small>{{ row.reason_codes.join('、') }}</small>
        </div>
        <label>
          纠正理由
          <textarea v-model="reason[row.id]" maxlength="1000" />
        </label>
        <div class="automatic-relationships__actions">
          <button type="button" :disabled="busy !== null" @click="withdraw(row)">撤销关系</button>
          <button type="button" :disabled="busy !== null" @click="keepIndependent(row)">保持独立</button>
          <button
            v-if="row.kind === 'MODEL_ALIAS' || row.kind === 'VERSION_SUCCESSOR'"
            type="button"
            :disabled="busy !== null"
            @click="correctModel(row)"
          >修正型号关系</button>
        </div>
      </li>
    </ol>
    <p v-else>当前没有生效中的自动关系。</p>

    <form class="automatic-relationships__split" @submit.prevent="splitEvent">
      <h3>拆分事件</h3>
      <p>把每条材料分配到事件 A 或事件 B；所有材料都必须分配。</p>
      <label v-for="(itemId, index) in itemIds" :key="itemId">
        <code>{{ itemId }}</code>
        <select v-model="splitGroups[itemId]">
          <option value="A">事件 A</option>
          <option value="B">事件 B</option>
        </select>
        <span v-if="splitGroups[itemId] === undefined">默认：{{ index === 0 ? '事件 A' : '事件 B' }}</span>
      </label>
      <label>拆分理由<textarea v-model="splitReason" maxlength="1000" /></label>
      <button type="submit" :disabled="busy !== null || itemIds.length < 2">拆分事件</button>
    </form>
  </section>
</template>

<style scoped>
.automatic-relationships { display: grid; padding: var(--spacing-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); gap: var(--spacing-4); }
.automatic-relationships header { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--spacing-3); }
.automatic-relationships h2, .automatic-relationships h3, .automatic-relationships p { margin: 0; }
.automatic-relationships ol { display: grid; margin: 0; padding: 0; list-style: none; gap: var(--spacing-3); }
.automatic-relationships li, .automatic-relationships__split { display: grid; padding: var(--spacing-4); background: var(--color-surfaceMuted); border-radius: var(--radius-md); gap: var(--spacing-3); }
.automatic-relationships li > div:first-child { display: grid; gap: var(--spacing-1); }
.automatic-relationships label { display: grid; gap: var(--spacing-1); color: var(--color-ink-700); }
.automatic-relationships textarea, .automatic-relationships select, .automatic-relationships button { min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-3); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); }
.automatic-relationships textarea { resize: vertical; }
.automatic-relationships__actions { display: flex; flex-wrap: wrap; gap: var(--spacing-2); }
@media (max-width: 47.999rem) { .automatic-relationships header { flex-direction: column; } }
</style>
