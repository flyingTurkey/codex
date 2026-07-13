<script setup lang="ts">
import { onBeforeUnmount, useId, watch } from 'vue'

import AppIcon from './AppIcon.vue'
import FocusTrap from './FocusTrap.vue'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    title: string
    description?: string
    side?: 'left' | 'right'
    closeLabel?: string
  }>(),
  {
    description: undefined,
    side: 'right',
    closeLabel: '关闭抽屉',
  },
)

const emit = defineEmits<{
  'update:modelValue': [open: boolean]
  close: []
}>()

const titleId = `srbg-drawer-title-${useId()}`
const descriptionId = `srbg-drawer-description-${useId()}`
let previousOverflow: string | undefined

function close(): void {
  emit('update:modelValue', false)
  emit('close')
}

function unlockBody(): void {
  if (typeof document === 'undefined' || previousOverflow === undefined) return
  document.body.style.overflow = previousOverflow
  previousOverflow = undefined
}

watch(
  () => props.modelValue,
  (open) => {
    if (typeof document === 'undefined') return
    if (open) {
      if (previousOverflow === undefined) previousOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'
    } else {
      unlockBody()
    }
  },
  { immediate: true },
)

onBeforeUnmount(unlockBody)
</script>

<template>
  <div v-if="modelValue" class="srbg-drawer" :data-side="side">
    <button
      class="srbg-drawer__backdrop"
      type="button"
      tabindex="-1"
      aria-label="关闭抽屉"
      @click="close"
    />
    <FocusTrap class="srbg-drawer__trap" :active="modelValue" initial-focus=".srbg-drawer__close" @escape="close">
      <section
        class="srbg-drawer__panel"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        :aria-describedby="description ? descriptionId : undefined"
      >
        <div class="srbg-drawer__header">
          <div>
            <h2 :id="titleId">{{ title }}</h2>
            <p v-if="description" :id="descriptionId">{{ description }}</p>
          </div>
          <button class="srbg-drawer__close" type="button" :aria-label="closeLabel" @click="close">
            <AppIcon name="Xmark" />
          </button>
        </div>
        <div class="srbg-drawer__content">
          <slot />
        </div>
        <footer v-if="$slots.footer" class="srbg-drawer__footer">
          <slot name="footer" />
        </footer>
      </section>
    </FocusTrap>
  </div>
</template>

<style scoped>
.srbg-drawer {
  position: fixed;
  z-index: 50;
  inset: 0;
  display: grid;
}

.srbg-drawer__backdrop {
  position: absolute;
  inset: 0;
  padding: 0;
  background: color-mix(in srgb, var(--color-ink-900) 42%, transparent);
  border: 0;
  cursor: default;
}

.srbg-drawer__trap {
  position: relative;
  width: min(var(--srbg-layout-detail-evidence), 100vw);
  height: 100%;
  overflow: hidden;
  justify-self: end;
}

.srbg-drawer[data-side='left'] .srbg-drawer__trap {
  justify-self: start;
}

.srbg-drawer__panel {
  position: absolute;
  inset: 0;
  display: grid;
  width: 100%;
  min-height: 0;
  grid-template-rows: auto minmax(0, 1fr) auto;
  color: var(--color-ink-700);
  background: var(--color-surface);
  box-shadow: var(--shadow-overlay);
}

.srbg-drawer__header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: var(--spacing-4);
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--color-border);
}

.srbg-drawer__header h2,
.srbg-drawer__header p {
  margin: 0;
}

.srbg-drawer__header h2 {
  color: var(--color-ink-900);
  font-size: var(--text-lg);
  line-height: var(--srbg-font-line-height-title);
}

.srbg-drawer__header p {
  margin-top: var(--spacing-1);
  color: var(--color-ink-600);
  font-size: var(--text-sm);
  line-height: var(--srbg-font-line-height-body);
}

.srbg-drawer__close {
  display: inline-grid;
  width: var(--spacing-9);
  height: var(--spacing-9);
  flex: none;
  place-items: center;
  padding: 0;
  color: var(--color-ink-700);
  background: var(--color-surfaceMuted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.srbg-drawer__close:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}

.srbg-drawer__content {
  min-height: 0;
  overflow-y: auto;
  padding: var(--spacing-5);
}

.srbg-drawer__footer {
  padding: var(--spacing-4) var(--spacing-5);
  border-top: 1px solid var(--color-border);
}

@media (prefers-reduced-motion: no-preference) {
  .srbg-drawer__trap {
    animation: srbg-drawer-enter var(--srbg-motion-drawer) var(--srbg-motion-easing);
  }

  @keyframes srbg-drawer-enter {
    from {
      opacity: 0;
      transform: translateX(2rem);
    }
  }

  .srbg-drawer[data-side='left'] .srbg-drawer__trap {
    animation-name: srbg-drawer-enter-left;
  }

  @keyframes srbg-drawer-enter-left {
    from {
      opacity: 0;
      transform: translateX(-2rem);
    }
  }
}
</style>
