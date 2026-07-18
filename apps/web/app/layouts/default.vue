<script setup lang="ts">
import type { MeResponse, PersonalSourceView } from '@srbg/contracts'
import { AppShell, type AppNavigationItem } from '@srbg/ui'
import { computed } from 'vue'

import { handleAppNavigation, personalNavigation, primaryNavigation } from '../navigation'

const route = useRoute()
const { data: identity } = await useFetch<MeResponse>('/api/v1/me', {
  retry: 0,
  timeout: 2_000,
})
const { data: healthSources, refresh: refreshHealth } = await useAsyncData<PersonalSourceView[]>(
  'personal-source-health-monitor',
  () => route.path === '/sources' && identity.value?.roles.includes('owner')
    ? $fetch<PersonalSourceView[]>('/api/v1/sources', { retry: 0, timeout: 5_000 })
    : Promise.resolve([]),
  { server: false, default: () => [] },
)
const healthCount = computed(() => actionableSourceCount(healthSources.value))
const { permission, requestPermission, supported } = usePersonalHealthNotifications(healthSources, refreshHealth)
watch(() => route.path, path => {
  if (path === '/sources' && identity.value?.roles.includes('owner')) void refreshHealth()
})

function handleNavigation(item: AppNavigationItem, event: MouseEvent): void {
  handleAppNavigation(item, event, (to) => navigateTo(to))
}
</script>

<template>
  <AppShell
    brand="四川路桥·智安情报"
    brand-subtitle="行业数智与安全情报平台"
    :primary-navigation="primaryNavigation"
    :admin-navigation="personalNavigation"
    :current-path="route.path"
    :show-admin="true"
    @navigate="handleNavigation"
  >
    <template #sidebar-footer>
      <section v-if="route.path === '/sources' && identity?.roles.includes('owner')" class="health-monitor" aria-label="来源健康通知">
        <NuxtLink to="/sources"><strong>来源异常 {{ healthCount }}</strong></NuxtLink>
        <div class="health-monitor__actions">
          <button v-if="supported && permission === 'default'" type="button" @click="requestPermission">启用通知</button>
          <button type="button" aria-label="刷新来源健康" @click="() => refreshHealth()">刷新健康</button>
        </div>
        <span v-if="permission === 'denied'">浏览器通知未授权</span>
        <span v-if="permission === 'granted'">仅通知健康状态变化</span>
      </section>
    </template>
    <template #mobile-header-actions>
      <NuxtLink v-if="route.path === '/sources' && identity?.roles.includes('owner')" class="health-count" to="/sources" :aria-label="`来源异常 ${healthCount}`">异常 {{ healthCount }}</NuxtLink>
    </template>
    <slot />
  </AppShell>
</template>

<style scoped>
.health-monitor { display: grid; padding: var(--spacing-3); gap: var(--spacing-2); font-size: var(--text-xs); }
.health-monitor a { color: var(--color-ink-900); }
.health-monitor button { min-height: var(--spacing-10); color: var(--color-brand-700); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-sm); }
.health-monitor__actions { display: grid; grid-template-columns: repeat(auto-fit, minmax(4rem, 1fr)); gap: var(--spacing-1); }
.health-monitor span { color: var(--color-ink-600); }
.health-count { padding: var(--spacing-2); color: var(--color-conflict-700); font-size: var(--text-sm); font-weight: var(--font-weight-semibold); }
</style>
