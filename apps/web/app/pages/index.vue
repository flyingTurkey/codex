<script setup lang="ts">
import type { VersionResponse } from '@srbg/contracts'

const config = useRuntimeConfig()
const { data: version, error } = await useAsyncData('api-version', () =>
  $fetch<VersionResponse>(`${config.internalApiBase}/api/v1/version`, {
    retry: 0,
    timeout: 2_000,
  }),
)

const apiReachable = computed(() => version.value !== undefined && error.value === undefined)
</script>

<template>
  <HomeDashboard :api-reachable="apiReachable" :version="version ?? null" />
</template>
