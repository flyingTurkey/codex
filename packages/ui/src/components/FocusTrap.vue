<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    active: boolean
    initialFocus?: string
  }>(),
  {
    initialFocus: undefined,
  },
)

const emit = defineEmits<{
  escape: [event: KeyboardEvent]
}>()

const container = ref<HTMLElement>()
let returnTarget: HTMLElement | null = null

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function focusableElements(): HTMLElement[] {
  if (!container.value) return []
  return Array.from(container.value.querySelectorAll<HTMLElement>(focusableSelector)).filter(isTabbable)
}

function isTabbable(element: HTMLElement): boolean {
  if (element.matches(':disabled')) return false
  if (element.closest('[hidden], [inert], [aria-hidden="true"], fieldset[disabled]')) return false
  if (element instanceof HTMLInputElement && element.type === 'hidden') return false

  let current: HTMLElement | null = element
  while (current) {
    const style = window.getComputedStyle(current)
    if (style.display === 'none' || style.visibility === 'hidden' || style.visibility === 'collapse') {
      return false
    }
    if (current === container.value) break
    current = current.parentElement
  }
  return true
}

function focusInitial(): void {
  if (!container.value) return
  const requested = props.initialFocus
    ? container.value.querySelector<HTMLElement>(props.initialFocus)
    : undefined
  const target = (requested && isTabbable(requested) ? requested : undefined) ?? focusableElements()[0] ?? container.value
  target.focus()
}

function restoreFocus(): void {
  if (returnTarget?.isConnected) returnTarget.focus()
  returnTarget = null
}

function handleKeydown(event: KeyboardEvent): void {
  if (!props.active) return
  if (event.key === 'Escape') {
    emit('escape', event)
    return
  }
  if (event.key !== 'Tab') return

  const focusable = focusableElements()
  if (focusable.length === 0) {
    event.preventDefault()
    container.value?.focus()
    return
  }

  const first = focusable[0]
  const last = focusable.at(-1)
  const activeElement = document.activeElement
  if (event.shiftKey && (activeElement === first || !container.value?.contains(activeElement))) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && (activeElement === last || !container.value?.contains(activeElement))) {
    event.preventDefault()
    first?.focus()
  }
}

watch(
  () => props.active,
  async (active, wasActive) => {
    if (typeof document === 'undefined') return
    if (active) {
      if (!wasActive && document.activeElement instanceof HTMLElement) {
        returnTarget = document.activeElement
      }
      await nextTick()
      focusInitial()
    } else if (wasActive) {
      await nextTick()
      restoreFocus()
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (props.active) restoreFocus()
})
</script>

<template>
  <div ref="container" class="srbg-focus-trap" tabindex="-1" @keydown="handleKeydown">
    <slot />
  </div>
</template>

<style scoped>
.srbg-focus-trap:focus {
  outline: none;
}
</style>
