<script setup lang="ts">
import type { MeResponse } from '@srbg/contracts'
import { AppShell, type AppNavigationItem } from '@srbg/ui'
import { computed } from 'vue'

import { adminNavigationForRoles, handleAppNavigation, primaryNavigation } from '../navigation'

const route = useRoute()
const { data: identity } = await useFetch<MeResponse>('/api/v1/me', {
  retry: 0,
  timeout: 2_000,
})
const visibleAdminNavigation = computed(() =>
  adminNavigationForRoles(identity.value?.roles ?? []),
)
const showAdmin = computed(() => visibleAdminNavigation.value.length > 0)

function handleNavigation(item: AppNavigationItem, event: MouseEvent): void {
  handleAppNavigation(item, event, (to) => navigateTo(to))
}
</script>

<template>
  <AppShell
    brand="四川路桥·智安情报"
    brand-subtitle="行业数智与安全情报平台"
    :primary-navigation="primaryNavigation"
    :admin-navigation="visibleAdminNavigation"
    :current-path="route.path"
    :show-admin="showAdmin"
    @navigate="handleNavigation"
  >
    <slot />
  </AppShell>
</template>
