<script setup lang="ts">
withDefaults(
  defineProps<{
    lines?: number
    label?: string
    animated?: boolean
  }>(),
  {
    lines: 1,
    label: '正在加载',
    animated: true,
  },
)
</script>

<template>
  <div
    class="srbg-skeleton"
    :class="{ 'srbg-skeleton--animated': animated }"
    role="status"
    :aria-label="label"
  >
    <span v-for="line in Math.max(1, lines)" :key="line" class="srbg-skeleton__line" />
  </div>
</template>

<style scoped>
.srbg-skeleton {
  display: grid;
  gap: var(--spacing-2);
}

.srbg-skeleton__line {
  display: block;
  width: 100%;
  height: var(--spacing-4);
  overflow: hidden;
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-sm);
}

.srbg-skeleton__line:last-child {
  width: 72%;
}

.srbg-skeleton--animated .srbg-skeleton__line {
  animation: srbg-skeleton-pulse 1.6s ease-in-out infinite;
}

@keyframes srbg-skeleton-pulse {
  50% {
    opacity: 0.48;
  }
}

@media (prefers-reduced-motion: reduce) {
  .srbg-skeleton--animated .srbg-skeleton__line {
    animation: none;
  }
}
</style>
