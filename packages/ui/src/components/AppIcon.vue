<script setup lang="ts">
import { computed } from 'vue'

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
    size: 20,
    strokeWidth: 1.5,
  },
)

const icon = computed(() => appIcons[props.name])
</script>

<template>
  <span
    class="srbg-icon"
    :data-icon="name"
    :role="label ? 'img' : undefined"
    :aria-label="label"
    :aria-hidden="label ? undefined : 'true'"
  >
    <component
      :is="icon"
      :width="size"
      :height="size"
      :stroke-width="strokeWidth"
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
</style>
