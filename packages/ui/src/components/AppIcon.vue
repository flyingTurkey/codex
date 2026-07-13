<script setup lang="ts">
import { computed } from 'vue'

import { designTokens } from '../generated/design-tokens'
import { appIcons, type AppIconName } from '../icons'

const props = withDefaults(
  defineProps<{
    name: AppIconName
    label?: string
    size?: number | string
    strokeWidth?: number | string
  }>(),
  {
    label: undefined,
    size: designTokens.icon.defaultSize,
    strokeWidth: designTokens.icon.defaultStroke,
  },
)

const icon = computed(() => appIcons[props.name])
const iconSize = computed(() => (typeof props.size === 'number' ? `${props.size}px` : props.size))
const iconStroke = computed(() =>
  typeof props.strokeWidth === 'number' ? `${props.strokeWidth}px` : props.strokeWidth,
)
</script>

<template>
  <span
    class="srbg-icon"
    :data-icon="name"
    :role="label ? 'img' : undefined"
    :aria-label="label"
    :aria-hidden="label ? undefined : 'true'"
    :style="{
      '--srbg-app-icon-size': iconSize,
      '--srbg-app-icon-stroke': iconStroke,
    }"
  >
    <component
      :is="icon"
      focusable="false"
    />
  </span>
</template>

<style scoped>
.srbg-icon {
  display: inline-flex;
  flex: none;
  line-height: 0;
}

.srbg-icon :deep(svg) {
  width: var(--srbg-app-icon-size);
  height: var(--srbg-app-icon-size);
  stroke-width: var(--srbg-app-icon-stroke);
}
</style>
