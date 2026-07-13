<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import type { AppNavigationItem } from '../types'

const props = withDefaults(
  defineProps<{
    brand: string
    brandSubtitle?: string
    primaryNavigation: readonly AppNavigationItem[]
    adminNavigation?: readonly AppNavigationItem[]
    currentPath: string
    showAdmin?: boolean
    compact?: boolean
    responsiveCompact?: boolean
  }>(),
  {
    brandSubtitle: undefined,
    adminNavigation: () => [],
    showAdmin: false,
    compact: false,
    responsiveCompact: false,
  },
)

const emit = defineEmits<{
  navigate: [item: AppNavigationItem, event: MouseEvent]
}>()

function isActive(item: AppNavigationItem): boolean {
  if (props.currentPath === item.to) return true
  return item.activePaths?.some(
    (path) => props.currentPath === path || props.currentPath.startsWith(path),
  ) ?? false
}
</script>

<template>
  <aside
    class="srbg-sidebar"
    :data-compact="compact || undefined"
    :data-responsive-compact="responsiveCompact || undefined"
  >
    <div class="srbg-sidebar__brand" :title="compact || responsiveCompact ? brand : undefined">
      <strong class="srbg-sidebar__brand-name">{{ brand }}</strong>
      <span v-if="brandSubtitle" class="srbg-sidebar__brand-subtitle">{{ brandSubtitle }}</span>
    </div>

    <nav class="srbg-sidebar__navigation" aria-label="主导航">
      <a
        v-for="item in primaryNavigation"
        :key="item.id"
        class="srbg-sidebar__link"
        :class="{ 'srbg-sidebar__link--active': isActive(item) }"
        :href="item.to"
        :aria-current="isActive(item) ? 'page' : undefined"
        :title="compact || responsiveCompact ? item.label : undefined"
        @click="emit('navigate', item, $event)"
      >
        <AppIcon :name="item.icon" />
        <span class="srbg-sidebar__label">{{ item.label }}</span>
      </a>
    </nav>

    <nav
      v-if="showAdmin && adminNavigation.length > 0"
      class="srbg-sidebar__navigation srbg-sidebar__navigation--admin"
      aria-label="管理导航"
    >
      <a
        v-for="item in adminNavigation"
        :key="item.id"
        class="srbg-sidebar__link"
        :class="{ 'srbg-sidebar__link--active': isActive(item) }"
        :href="item.to"
        :aria-current="isActive(item) ? 'page' : undefined"
        :title="compact || responsiveCompact ? item.label : undefined"
        @click="emit('navigate', item, $event)"
      >
        <AppIcon :name="item.icon" />
        <span class="srbg-sidebar__label">{{ item.label }}</span>
      </a>
    </nav>

    <footer v-if="$slots.footer" class="srbg-sidebar__footer">
      <slot name="footer" />
    </footer>
  </aside>
</template>

<style scoped>
.srbg-sidebar {
  box-sizing: border-box;
  display: flex;
  width: 100%;
  min-height: 100%;
  flex-direction: column;
  gap: var(--spacing-4);
  padding: var(--spacing-5) var(--spacing-3);
  color: var(--color-ink-700);
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
}

.srbg-sidebar__brand {
  display: grid;
  gap: var(--spacing-1);
  min-height: var(--spacing-12);
  padding: 0 var(--spacing-3);
}

.srbg-sidebar__brand-name {
  color: var(--color-ink-900);
  font-size: var(--text-base);
  line-height: var(--srbg-font-line-height-title);
}

.srbg-sidebar__brand-subtitle {
  color: var(--color-ink-500);
  font-size: var(--text-xs);
  line-height: var(--srbg-font-line-height-metadata);
}

.srbg-sidebar__navigation {
  display: grid;
  gap: var(--spacing-1);
}

.srbg-sidebar__navigation--admin {
  margin-top: auto;
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--color-border);
}

.srbg-sidebar__link {
  display: flex;
  min-height: calc(var(--spacing-12) + var(--spacing-1));
  align-items: center;
  gap: var(--spacing-3);
  padding: 0 var(--spacing-3);
  color: var(--color-ink-700);
  font-size: var(--text-base);
  font-weight: var(--font-weight-medium);
  text-decoration: none;
  border-radius: var(--radius-md);
  transition:
    color var(--srbg-motion-fast) var(--srbg-motion-easing),
    background-color var(--srbg-motion-fast) var(--srbg-motion-easing);
}

.srbg-sidebar__link:hover {
  color: var(--color-ink-900);
  background: var(--color-surfaceMuted);
}

.srbg-sidebar__link--active {
  color: var(--color-brand-700);
  background: var(--color-brand-100);
}

.srbg-sidebar__link:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}

.srbg-sidebar__footer {
  padding: var(--spacing-3);
  color: var(--color-ink-600);
  font-size: var(--text-sm);
  border-top: 1px solid var(--color-border);
}

.srbg-sidebar[data-compact] {
  align-items: stretch;
  padding-inline: var(--spacing-2);
}

.srbg-sidebar[data-compact] .srbg-sidebar__brand {
  overflow: hidden;
  padding-inline: 0;
  text-align: center;
}

.srbg-sidebar[data-compact] .srbg-sidebar__brand-name,
.srbg-sidebar[data-compact] .srbg-sidebar__brand-subtitle,
.srbg-sidebar[data-compact] .srbg-sidebar__label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  clip-path: inset(50%);
}

.srbg-sidebar[data-compact] .srbg-sidebar__link {
  justify-content: center;
  padding-inline: 0;
}

@media (min-width: 64rem) and (max-width: 79.999rem) {
  .srbg-sidebar[data-responsive-compact] {
    align-items: stretch;
    padding-inline: var(--spacing-2);
  }

  .srbg-sidebar[data-responsive-compact] .srbg-sidebar__brand {
    overflow: hidden;
    padding-inline: 0;
    text-align: center;
  }

  .srbg-sidebar[data-responsive-compact] .srbg-sidebar__brand-name,
  .srbg-sidebar[data-responsive-compact] .srbg-sidebar__brand-subtitle,
  .srbg-sidebar[data-responsive-compact] .srbg-sidebar__label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    clip-path: inset(50%);
  }

  .srbg-sidebar[data-responsive-compact] .srbg-sidebar__link {
    justify-content: center;
    padding-inline: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .srbg-sidebar__link {
    transition: none;
  }
}
</style>
