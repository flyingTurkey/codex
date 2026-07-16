<script setup lang="ts">
import { ResponsiveDrawer } from '@srbg/ui'
import { computed, ref } from 'vue'

import type { SourceLifecycleAction, SourceLifecycleDisplayState } from '../source-center'

const props = withDefaults(
  defineProps<{
    availableActions: readonly SourceLifecycleAction[]
    busy?: boolean
    lifecycleState: SourceLifecycleDisplayState
  }>(),
  { busy: false },
)

const emit = defineEmits<{
  command: [payload: { action: SourceLifecycleAction, reason: string }]
}>()

interface ActionPresentation {
  readonly action: SourceLifecycleAction
  readonly buttonLabel: string
  readonly confirmLabel: string
  readonly description: string
  readonly tone: 'danger' | 'primary' | 'secondary'
}

const commandPresentations: readonly ActionPresentation[] = [
  {
    action: 'SUBMIT_COMPLIANCE',
    buttonLabel: '提交合规复核',
    confirmLabel: '确认提交',
    description: '服务端会重新校验准入材料；客户端不能指定目标状态。',
    tone: 'primary',
  },
  {
    action: 'PAUSE',
    buttonLabel: '暂停来源',
    confirmLabel: '确认暂停',
    description: '暂停后不再生成新调度；历史证据与审计记录继续保留。',
    tone: 'danger',
  },
  {
    action: 'RESUME',
    buttonLabel: '恢复来源',
    confirmLabel: '确认恢复',
    description: '服务端会重新校验当前策略、配置、审批与试运行，不保证恢复为 ACTIVE。',
    tone: 'primary',
  },
  {
    action: 'RETIRE',
    buttonLabel: '退役来源',
    confirmLabel: '确认退役',
    description: '退役是终态；不会删除历史原始证据、状态事件或审计事实。',
    tone: 'danger',
  },
]

const visibleActions = computed(() => commandPresentations.filter(presentation =>
  props.availableActions.includes(presentation.action),
))
const selected = ref<ActionPresentation | null>(null)
const reason = ref('')

function openCommand(presentation: ActionPresentation): void {
  selected.value = presentation
  reason.value = ''
}

function closeCommand(): void {
  selected.value = null
  reason.value = ''
}

function submitCommand(): void {
  if (!selected.value || !reason.value.trim()) return
  emit('command', { action: selected.value.action, reason: reason.value.trim() })
  closeCommand()
}
</script>

<template>
  <div class="lifecycle-controls" :data-lifecycle-state="lifecycleState">
    <button
      v-for="presentation in visibleActions"
      :key="presentation.action"
      :class="`${presentation.tone}-button`"
      type="button"
      :data-action="presentation.action"
      :disabled="busy"
      @click="openCommand(presentation)"
    >
      {{ presentation.buttonLabel }}
    </button>

    <ResponsiveDrawer
      :model-value="selected !== null"
      :title="selected?.buttonLabel ?? '来源生命周期操作'"
      :description="selected?.description"
      @update:model-value="open => { if (!open) closeCommand() }"
    >
      <form id="source-lifecycle-command" class="command-form" @submit.prevent="submitCommand">
        <label for="source-action-reason">操作原因</label>
        <textarea
          id="source-action-reason"
          v-model.trim="reason"
          name="action-reason"
          required
          minlength="2"
          maxlength="500"
          rows="5"
        />
        <p class="evidence-note">
          当前状态：{{ lifecycleState }}。最终状态与运行授权由服务端权威计算。
        </p>
      </form>
      <template #footer>
        <div class="drawer-actions">
          <button class="secondary-button" type="button" @click="closeCommand">取消</button>
          <button
            class="primary-button"
            type="submit"
            form="source-lifecycle-command"
            :disabled="busy || !reason.trim()"
          >
            {{ selected?.confirmLabel ?? '确认' }}
          </button>
        </div>
      </template>
    </ResponsiveDrawer>
  </div>
</template>

<style scoped>
.lifecycle-controls,
.drawer-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--spacing-2);
}

.command-form {
  display: grid;
  gap: var(--spacing-2);
}

.command-form label {
  color: var(--color-ink-700);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
}

.command-form textarea {
  width: 100%;
  padding: var(--spacing-3);
  color: var(--color-ink-900);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
  resize: vertical;
}

.evidence-note {
  margin: 0;
  padding: var(--spacing-3);
  color: var(--color-ink-700);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
}

.primary-button,
.secondary-button,
.danger-button {
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-4);
  font-weight: var(--font-weight-semibold);
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.primary-button {
  color: var(--color-surface);
  background: var(--color-brand-700);
  border-color: var(--color-brand-700);
}

.secondary-button {
  color: var(--color-brand-700);
  background: var(--color-surface);
}

.danger-button {
  color: var(--color-conflict-700);
  background: var(--color-conflict-50);
}

button:disabled {
  cursor: wait;
  opacity: 0.6;
}
</style>
