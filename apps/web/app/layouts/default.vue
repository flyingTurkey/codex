<script setup lang="ts">
import { AppShell, type AppNavigationItem } from '@srbg/ui'

import { adminNavigation, handleAppNavigation, primaryNavigation } from '../navigation'

const route = useRoute()
const showAdmin = false

function handleNavigation(item: AppNavigationItem, event: MouseEvent): void {
  handleAppNavigation(item, event, (to) => navigateTo(to))
}
</script>

<template>
  <AppShell
    brand="四川路桥·智安情报"
    brand-subtitle="行业数智与安全情报平台"
    :primary-navigation="primaryNavigation"
    :admin-navigation="adminNavigation"
    :current-path="route.path"
    :show-admin="showAdmin"
    @navigate="handleNavigation"
  >
    <slot />
  </AppShell>
</template>
