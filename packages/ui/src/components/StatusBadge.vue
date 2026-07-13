<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from './AppIcon.vue'
import type { AppIconName } from '../icons'
import type { StatusBadgeTone } from '../types'

const props = defineProps<{
  tone: StatusBadgeTone
  label: string
}>()

const toneIcons: Readonly<Record<StatusBadgeTone, AppIconName>> = {
  healthy: 'CheckCircle',
  degraded: 'WarningCircle',
  verified: 'ShieldCheck',
  pending: 'Clock',
  vendor: 'Reports',
  conflict: 'WarningCircle',
  withdrawn: 'Xmark',
  info: 'InfoCircle',
}

const icon = computed(() => toneIcons[props.tone])
</script>

<template>
  <span class="srbg-status-badge" :data-tone="tone">
    <AppIcon :name="icon" />
    <span>{{ label }}</span>
  </span>
</template>

<style scoped>
.srbg-status-badge {
  display: inline-flex;
  width: fit-content;
  min-height: var(--spacing-7);
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
  color: var(--badge-foreground);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
  line-height: var(--srbg-font-line-height-metadata);
  background: var(--badge-background);
  border: 1px solid currentColor;
  border-radius: var(--radius-pill);
}

.srbg-status-badge[data-tone='healthy'],
.srbg-status-badge[data-tone='verified'] {
  --badge-foreground: var(--color-verified-700);
  --badge-background: var(--color-verified-50);
}

.srbg-status-badge[data-tone='degraded'],
.srbg-status-badge[data-tone='pending'] {
  --badge-foreground: var(--color-reviewPending-700);
  --badge-background: var(--color-reviewPending-50);
}

.srbg-status-badge[data-tone='vendor'] {
  --badge-foreground: var(--color-vendorClaim-700);
  --badge-background: var(--color-vendorClaim-50);
}

.srbg-status-badge[data-tone='conflict'],
.srbg-status-badge[data-tone='withdrawn'] {
  --badge-foreground: var(--color-conflict-700);
  --badge-background: var(--color-conflict-50);
}

.srbg-status-badge[data-tone='info'] {
  --badge-foreground: var(--color-digital-700);
  --badge-background: var(--color-digital-50);
}
</style>
