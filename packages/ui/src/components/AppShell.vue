<script setup lang="ts">
import { ref } from 'vue'

import AppIcon from './AppIcon.vue'
import AppSidebar from './AppSidebar.vue'
import ResponsiveDrawer from './ResponsiveDrawer.vue'
import type { AppNavigationItem } from '../types'

withDefaults(
  defineProps<{
    brand: string
    brandSubtitle?: string
    primaryNavigation: readonly AppNavigationItem[]
    adminNavigation?: readonly AppNavigationItem[]
    currentPath: string
    showAdmin?: boolean
  }>(),
  {
    brandSubtitle: undefined,
    adminNavigation: () => [],
    showAdmin: false,
  },
)

const mobileNavigationOpen = ref(false)
</script>

<template>
  <div class="srbg-app-shell">
    <a class="srbg-skip-link" href="#main-content">跳到主内容</a>

    <div class="srbg-app-shell__desktop-sidebar">
      <AppSidebar
        :brand="brand"
        :brand-subtitle="brandSubtitle"
        :primary-navigation="primaryNavigation"
        :admin-navigation="adminNavigation"
        :current-path="currentPath"
        :show-admin="showAdmin"
      >
        <template v-if="$slots['sidebar-footer']" #footer>
          <slot name="sidebar-footer" />
        </template>
      </AppSidebar>
    </div>

    <header class="srbg-app-shell__mobile-header">
      <button
        class="srbg-app-shell__menu"
        type="button"
        aria-label="打开导航"
        aria-haspopup="dialog"
        :aria-expanded="mobileNavigationOpen"
        @click="mobileNavigationOpen = true"
      >
        <AppIcon name="Menu" />
      </button>
      <strong>{{ brand }}</strong>
      <slot name="mobile-header-actions" />
    </header>

    <main id="main-content" class="srbg-app-shell__main" tabindex="-1">
      <slot />
    </main>

    <ResponsiveDrawer v-model="mobileNavigationOpen" :title="brand" side="left">
      <AppSidebar
        :brand="brand"
        :brand-subtitle="brandSubtitle"
        :primary-navigation="primaryNavigation"
        :admin-navigation="adminNavigation"
        :current-path="currentPath"
        :show-admin="showAdmin"
        @navigate="mobileNavigationOpen = false"
      >
        <template v-if="$slots['sidebar-footer']" #footer>
          <slot name="sidebar-footer" />
        </template>
      </AppSidebar>
    </ResponsiveDrawer>
  </div>
</template>

<style scoped>
.srbg-app-shell {
  display: grid;
  min-height: 100dvh;
  grid-template-columns: var(--srbg-layout-sidebar) minmax(0, 1fr);
  color: var(--color-ink-700);
  font-family: var(--font-sans);
  background: var(--color-canvas);
}

.srbg-skip-link {
  position: fixed;
  z-index: 100;
  top: var(--spacing-2);
  left: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-surface);
  background: var(--color-brand-700);
  border-radius: var(--radius-sm);
  transform: translateY(-200%);
}

.srbg-skip-link:focus {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
  transform: translateY(0);
}

.srbg-app-shell__desktop-sidebar {
  position: sticky;
  top: 0;
  height: 100dvh;
}

.srbg-app-shell__main {
  min-width: 0;
  padding: var(--spacing-9);
}

.srbg-app-shell__main:focus {
  outline: none;
}

.srbg-app-shell__mobile-header {
  display: none;
}

@media (min-width: 64rem) and (max-width: 79.999rem) {
  .srbg-app-shell {
    grid-template-columns: var(--srbg-layout-sidebar-compact) minmax(0, 1fr);
  }

  .srbg-app-shell__desktop-sidebar :deep(.srbg-sidebar__brand-name),
  .srbg-app-shell__desktop-sidebar :deep(.srbg-sidebar__brand-subtitle),
  .srbg-app-shell__desktop-sidebar :deep(.srbg-sidebar__label) {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    clip-path: inset(50%);
  }

  .srbg-app-shell__desktop-sidebar :deep(.srbg-sidebar__link) {
    justify-content: center;
    padding-inline: 0;
  }

  .srbg-app-shell__main {
    padding: var(--spacing-7);
  }
}

@media (max-width: 63.999rem) {
  .srbg-app-shell {
    display: block;
  }

  .srbg-app-shell__desktop-sidebar {
    display: none;
  }

  .srbg-app-shell__mobile-header {
    position: sticky;
    z-index: 20;
    top: 0;
    display: grid;
    min-height: var(--srbg-layout-header);
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--spacing-3);
    padding: var(--spacing-2) var(--spacing-4);
    color: var(--color-ink-900);
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-border);
  }

  .srbg-app-shell__menu {
    display: inline-grid;
    width: var(--spacing-10);
    height: var(--spacing-10);
    place-items: center;
    padding: 0;
    color: var(--color-ink-700);
    background: var(--color-surfaceMuted);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
  }

  .srbg-app-shell__menu:focus-visible {
    outline: 2px solid var(--color-focus);
    outline-offset: 2px;
  }

  .srbg-app-shell__main {
    padding: var(--spacing-4);
  }
}

@media (prefers-reduced-motion: reduce) {
  .srbg-skip-link {
    transition: none;
  }
}
</style>
