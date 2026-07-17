<script setup lang="ts">
import type { SourceWorkspaceView } from '../source-center'

const props = defineProps<{
  activeView: SourceWorkspaceView
  counts: Readonly<Record<SourceWorkspaceView, number>>
}>()

const emit = defineEmits<{
  change: [view: SourceWorkspaceView]
}>()

const tabs: readonly { label: string, view: SourceWorkspaceView }[] = [
  { label: '候选来源', view: 'candidates' },
  { label: '已启用来源', view: 'enabled' },
  { label: '需处理', view: 'attention' },
]

function select(view: SourceWorkspaceView): void {
  if (view !== props.activeView) emit('change', view)
}

function moveFocus(event: KeyboardEvent, index: number): void {
  const container = (event.currentTarget as HTMLElement | null)?.parentElement
  const buttons = container
    ? [...container.querySelectorAll<HTMLButtonElement>('[role="tab"]')]
    : []
  if (!buttons.length) return

  let target = index
  if (event.key === 'ArrowRight') target = (index + 1) % buttons.length
  else if (event.key === 'ArrowLeft') target = (index - 1 + buttons.length) % buttons.length
  else if (event.key === 'Home') target = 0
  else if (event.key === 'End') target = buttons.length - 1
  else return

  event.preventDefault()
  buttons[target]?.focus()
  select(tabs[target]!.view)
}
</script>

<template>
  <div class="source-workspace-tabs" role="tablist" aria-label="来源中心工作区">
    <button
      v-for="(tab, index) in tabs"
      :id="`source-workspace-tab-${tab.view}`"
      :key="tab.view"
      class="source-workspace-tabs__tab"
      type="button"
      role="tab"
      :aria-label="`${tab.label} ${counts[tab.view]}`"
      :aria-controls="`source-workspace-panel-${tab.view}`"
      :aria-selected="activeView === tab.view"
      :data-active="activeView === tab.view"
      :tabindex="activeView === tab.view ? 0 : -1"
      @click="select(tab.view)"
      @keydown="moveFocus($event, index)"
    >
      <span>{{ tab.label }}</span>
      <span class="source-workspace-tabs__count">{{ counts[tab.view] }}</span>
    </button>
  </div>
</template>

<style scoped>
.source-workspace-tabs {
  display: flex;
  overflow-x: auto;
  padding: var(--spacing-1);
  background: var(--color-surfaceMuted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  gap: var(--spacing-1);
}

.source-workspace-tabs__tab {
  display: inline-flex;
  min-height: var(--spacing-10);
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2) var(--spacing-4);
  color: var(--color-ink-600);
  white-space: nowrap;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  gap: var(--spacing-2);
}

.source-workspace-tabs__tab[data-active='true'] {
  color: var(--color-brand-800);
  background: var(--color-surface);
  border-color: var(--color-borderStrong);
  box-shadow: var(--shadow-card);
}

.source-workspace-tabs__count {
  min-width: var(--spacing-6);
  padding-inline: var(--spacing-1);
  color: var(--color-ink-600);
  background: var(--color-ink-100);
  border-radius: var(--radius-pill);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}
</style>
