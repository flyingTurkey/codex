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

const semanticTabStopSelectors = [
  'area[href]',
  'summary',
  '[contenteditable]:not([contenteditable="false"])',
  'audio[controls]',
  'video[controls]',
  'iframe',
  'object',
  'embed',
]
const semanticTabStopSelector = semanticTabStopSelectors.join(',')
const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  ...semanticTabStopSelectors,
  '[tabindex]',
].join(',')

function focusableElements(): HTMLElement[] {
  if (!container.value) return []
  const candidates = Array.from(
    container.value.querySelectorAll<HTMLElement>(focusableSelector),
  ).filter(isTabStop)

  const radioTabStops = candidates.filter((element) => {
    if (!(element instanceof HTMLInputElement) || element.type !== 'radio' || !element.name) {
      return true
    }
    const group = candidates.filter(
      (candidate): candidate is HTMLInputElement =>
        candidate instanceof HTMLInputElement &&
        candidate.type === 'radio' &&
        candidate.name === element.name &&
        candidate.form === element.form,
    )
    return element === (group.find((radio) => radio.checked) ?? group[0])
  })

  return radioTabStops
    .map((element, domIndex) => ({ element, domIndex }))
    .sort((left, right) => {
      const leftTabIndex = left.element.tabIndex
      const rightTabIndex = right.element.tabIndex
      if (leftTabIndex > 0 && rightTabIndex <= 0) return -1
      if (leftTabIndex <= 0 && rightTabIndex > 0) return 1
      if (leftTabIndex > 0 && rightTabIndex > 0 && leftTabIndex !== rightTabIndex) {
        return leftTabIndex - rightTabIndex
      }
      return left.domIndex - right.domIndex
    })
    .map(({ element }) => element)
}

function isTabStop(element: HTMLElement): boolean {
  if (!isAvailableFocusTarget(element)) return false
  if (element.tabIndex >= 0) return true
  return !element.hasAttribute('tabindex') && element.matches(semanticTabStopSelector)
}

function isAvailableFocusTarget(element: HTMLElement): boolean {
  if (element.matches(':disabled')) return false
  if (element.closest('[hidden], [inert], [aria-hidden="true"]')) return false
  if (element instanceof HTMLInputElement && element.type === 'hidden') return false
  if (isDisabledByFieldset(element) || isCollapsedByClosedDetails(element)) return false

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

function isDisabledByFieldset(element: HTMLElement): boolean {
  let ancestor = element.parentElement
  while (ancestor && ancestor !== container.value) {
    if (ancestor instanceof HTMLFieldSetElement && ancestor.disabled) {
      const firstLegend = Array.from(ancestor.children).find(
        (child): child is HTMLLegendElement => child instanceof HTMLLegendElement,
      )
      if (!firstLegend?.contains(element)) return true
    }
    ancestor = ancestor.parentElement
  }
  return false
}

function isCollapsedByClosedDetails(element: HTMLElement): boolean {
  let ancestor = element.parentElement
  while (ancestor && ancestor !== container.value) {
    if (ancestor instanceof HTMLDetailsElement && !ancestor.open) {
      const firstSummary = Array.from(ancestor.children).find(
        (child): child is HTMLElement => child instanceof HTMLElement && child.tagName === 'SUMMARY',
      )
      if (!firstSummary?.contains(element)) return true
    }
    ancestor = ancestor.parentElement
  }
  return false
}

function isProgrammaticallyFocusable(element: HTMLElement): boolean {
  return (
    isAvailableFocusTarget(element) &&
    (element.tabIndex >= 0 ||
      element.hasAttribute('tabindex') ||
      element.matches(semanticTabStopSelector))
  )
}

function focusFallback(): void {
  if (!container.value) return
  const fallback = focusableElements()[0] ?? container.value
  fallback.focus()
  if (document.activeElement !== fallback && fallback !== container.value) container.value.focus()
}

function focusInitial(): void {
  if (!container.value) return
  const requested = props.initialFocus
    ? container.value.querySelector<HTMLElement>(props.initialFocus)
    : undefined
  if (requested && isProgrammaticallyFocusable(requested)) {
    requested.focus()
    if (document.activeElement === requested) return
  }
  focusFallback()
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
      if (!wasActive) document.addEventListener('keydown', handleKeydown)
      if (!wasActive && document.activeElement instanceof HTMLElement) {
        returnTarget = document.activeElement
      }
      await nextTick()
      focusInitial()
    } else if (wasActive) {
      document.removeEventListener('keydown', handleKeydown)
      await nextTick()
      restoreFocus()
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (typeof document !== 'undefined') document.removeEventListener('keydown', handleKeydown)
  if (props.active) restoreFocus()
})
</script>

<template>
  <div ref="container" class="srbg-focus-trap" tabindex="-1">
    <slot />
  </div>
</template>

<style scoped>
.srbg-focus-trap:focus {
  outline: none;
}
</style>
