<script setup lang="ts">
import { AppShell } from '@srbg/ui'

import { adminNavigation, primaryNavigation } from '../navigation'

const route = useRoute()
const showAdmin = false
</script>

<template>
  <AppShell
    brand="四川路桥·智安情报"
    brand-subtitle="行业数智与安全情报平台"
    :primary-navigation="primaryNavigation"
    :admin-navigation="adminNavigation"
    :current-path="route.path"
    :show-admin="showAdmin"
  >
    <slot />
  </AppShell>
</template>
