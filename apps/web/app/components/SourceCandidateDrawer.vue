<script setup lang="ts">
import { ResponsiveDrawer, StatusBadge } from '@srbg/ui'
import { computed, ref, watch } from 'vue'

import type { SourceCandidateCardProjection } from '../source-center'
import {
  candidateCanDismiss,
  candidateCanEnable,
  formatShanghaiDateTime,
  qualificationVerdictLabel,
  qualificationVerdictTone,
} from '../source-center'

const props = withDefaults(defineProps<{
  busy?: boolean
  candidate: SourceCandidateCardProjection
  initialDecision?: '' | 'DISMISS' | 'ENABLE'
  modelValue: boolean
  roles: readonly string[]
}>(), {
  busy: false,
  initialDecision: '',
})

const emit = defineEmits<{
  decision: [payload: {
    decision: 'DISMISS' | 'ENABLE'
    reason: string
    waiverReason?: string
  }]
  'update:modelValue': [open: boolean]
}>()

const AUTOMATED_DECISION_REASONS = {
  DISMISS: '不启用当前候选来源',
  ENABLE: '启用当前服务端资格审核通过的候选来源',
  ENABLE_WITH_WAIVER: '豁免警告并启用当前候选来源',
} as const

const selectedDecision = ref<'' | 'DISMISS' | 'ENABLE'>('')
const waiverReason = ref('')

const canDismiss = computed(() => candidateCanDismiss(props.candidate, props.roles))
const canEnable = computed(() => candidateCanEnable(props.candidate, props.roles))
const requiresWaiver = computed(() => (
  selectedDecision.value === 'ENABLE'
  && props.candidate.latest_qualification?.verdict === 'WARN_WAIVABLE'
))
const canSubmit = computed(() => (
  !props.busy
  && selectedDecision.value !== ''
  && (!requiresWaiver.value || waiverReason.value.trim().length >= 2)
))

watch(
  () => [props.modelValue, props.candidate.id] as const,
  ([open]) => {
    if (!open) return
    selectedDecision.value = props.initialDecision
    waiverReason.value = ''
  },
  { immediate: true },
)

function close(): void {
  emit('update:modelValue', false)
}

function choose(decision: 'DISMISS' | 'ENABLE'): void {
  selectedDecision.value = decision
  waiverReason.value = ''
}

function submit(): void {
  if (!canSubmit.value || !selectedDecision.value) return
  emit('decision', {
    decision: selectedDecision.value,
    reason: requiresWaiver.value
      ? AUTOMATED_DECISION_REASONS.ENABLE_WITH_WAIVER
      : AUTOMATED_DECISION_REASONS[selectedDecision.value],
    ...(requiresWaiver.value ? { waiverReason: waiverReason.value.trim() } : {}),
  })
}
</script>

<template>
  <ResponsiveDrawer
    :model-value="modelValue"
    :title="candidate.institution_name"
    description="决定只绑定当前服务端资格包；证据或规则变化后必须重新确认。"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="candidate-drawer">
      <div class="candidate-drawer__status">
        <StatusBadge
          :tone="qualificationVerdictTone(candidate)"
          :label="qualificationVerdictLabel(candidate)"
        />
        <span>{{ candidate.latest_qualification?.rule_version ?? '规则待运行' }}</span>
      </div>

      <dl class="candidate-drawer__facts">
        <div><dt>授权边界</dt><dd>{{ candidate.authorization_boundary }}</dd></div>
        <div><dt>候选状态</dt><dd>{{ candidate.status }}</dd></div>
        <div><dt>证据存储</dt><dd>{{ candidate.latest_qualification?.storage_policy ?? '未决定' }}</dd></div>
        <div><dt>证据采集</dt><dd>{{ candidate.latest_qualification?.evidence_capture_policy ?? '未决定' }}</dd></div>
        <div><dt>资格有效期</dt><dd>{{ formatShanghaiDateTime(candidate.latest_qualification?.expires_at) }}</dd></div>
        <div><dt>材料指纹</dt><dd>{{ candidate.latest_qualification?.material_fingerprint ?? '缺失' }}</dd></div>
        <div><dt>资格包</dt><dd>{{ candidate.latest_qualification?.bundle_sha256 ?? '缺失' }}</dd></div>
      </dl>

      <section v-if="candidate.latest_qualification?.checks?.length" aria-labelledby="qualification-checks-title">
        <h3 id="qualification-checks-title">资格检查</h3>
        <ul class="candidate-drawer__checks">
          <li v-for="check in candidate.latest_qualification.checks" :key="`${check.code}:${check.observed_at}`">
            <div>
              <StatusBadge
                :tone="check.level === 'PASS' ? 'healthy' : check.level === 'WARN' ? 'degraded' : 'conflict'"
                :label="check.level"
              />
              <strong>{{ check.message }}</strong>
            </div>
            <p>{{ check.code }} · {{ formatShanghaiDateTime(check.observed_at) }}</p>
            <ul v-if="check.evidence_refs?.length" aria-label="检查证据定位">
              <li v-for="reference in check.evidence_refs" :key="reference">{{ reference }}</li>
            </ul>
          </li>
        </ul>
      </section>

      <p
        v-if="candidate.latest_qualification?.verdict === 'BLOCKED'"
        class="candidate-drawer__block"
        role="alert"
      >
        硬阻断不能由管理员绕过。修复访问、权利或安全问题后必须重新执行资格审核。
      </p>

      <div v-if="canEnable || canDismiss" class="candidate-drawer__choices" aria-label="候选决定">
        <button
          v-if="canEnable"
          class="primary-button"
          data-select-decision="ENABLE"
          type="button"
          :aria-pressed="selectedDecision === 'ENABLE'"
          :disabled="busy"
          @click="choose('ENABLE')"
        >
          启用
        </button>
        <button
          v-if="canDismiss"
          class="secondary-button"
          data-select-decision="DISMISS"
          type="button"
          :aria-pressed="selectedDecision === 'DISMISS'"
          :disabled="busy"
          @click="choose('DISMISS')"
        >
          不启用
        </button>
      </div>
      <p v-else-if="candidate.latest_qualification?.verdict !== 'BLOCKED'" role="note">
        当前角色可以查看资格证据，但不能作出最终启用或不启用决定。
      </p>

      <form v-if="requiresWaiver" id="candidate-decision-form" @submit.prevent="submit">
        <label>
          豁免理由
          <textarea
            v-model.trim="waiverReason"
            name="waiver-reason"
            required
            minlength="2"
            maxlength="1000"
            rows="5"
          />
        </label>
        <p v-if="requiresWaiver" class="candidate-drawer__warning" role="note">
          警告候选只能逐项启用；请说明受限题录的展示边界。规则、域名或条款变化后豁免自动失效。
        </p>
      </form>
    </div>

    <template #footer>
      <div class="candidate-drawer__footer">
        <button class="secondary-button" type="button" @click="close">取消</button>
        <button
          v-if="selectedDecision"
          class="primary-button"
          data-submit-decision
          type="button"
          :disabled="!canSubmit"
          @click="submit"
        >
          {{ selectedDecision === 'ENABLE' ? '确认启用' : '确认不启用' }}
        </button>
      </div>
    </template>
  </ResponsiveDrawer>
</template>

<style scoped>
.candidate-drawer,
#candidate-decision-form {
  display: grid;
  gap: var(--spacing-4);
}

.candidate-drawer__status,
.candidate-drawer__choices,
.candidate-drawer__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--spacing-2);
}

.candidate-drawer__status {
  justify-content: space-between;
  color: var(--color-ink-600);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.candidate-drawer__facts {
  display: grid;
  margin: 0;
  gap: var(--spacing-2);
}

.candidate-drawer__facts div {
  display: grid;
  grid-template-columns: 7rem minmax(0, 1fr);
  padding-block: var(--spacing-2);
  border-bottom: 1px solid var(--color-border);
  gap: var(--spacing-3);
}

.candidate-drawer__facts dt {
  color: var(--color-ink-600);
  font-size: var(--text-sm);
}

.candidate-drawer__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--color-ink-900);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

#qualification-checks-title {
  margin: 0 0 var(--spacing-2);
  color: var(--color-ink-900);
  font-size: var(--text-base);
}

.candidate-drawer__checks,
.candidate-drawer__checks ul {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
  gap: var(--spacing-2);
}

.candidate-drawer__checks > li {
  padding: var(--spacing-3);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-sm);
}

.candidate-drawer__checks > li > div {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.candidate-drawer__checks p,
.candidate-drawer__checks ul {
  margin-top: var(--spacing-2);
  color: var(--color-ink-600);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.candidate-drawer__checks ul li {
  overflow-wrap: anywhere;
}

.candidate-drawer__block,
.candidate-drawer__warning {
  margin: 0;
  padding: var(--spacing-3);
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
}

#candidate-decision-form label {
  display: grid;
  color: var(--color-ink-700);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
  gap: var(--spacing-1);
}

#candidate-decision-form textarea {
  width: 100%;
  padding: var(--spacing-3);
  color: var(--color-ink-900);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
  resize: vertical;
}

.candidate-drawer__footer {
  justify-content: flex-end;
}

.primary-button,
.secondary-button {
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-4);
  border: 1px solid var(--color-brand-700);
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

.primary-button {
  color: var(--color-surface);
  background: var(--color-brand-700);
}

.secondary-button {
  color: var(--color-brand-700);
  background: var(--color-surface);
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
</style>
