<script setup lang="ts">
type ProviderView = {
  code: string
  base_url: string
  request_path: string
  models: string[]
  real_call_enabled: boolean
  key_configured: boolean
  runtime_status: string
  blocking_reasons: string[]
}

const notice = ref<string | null>(null)
const { data, error, refresh } = await useFetch<ProviderView[]>('/api/v1/admin/ai/providers', {
  server: false,
  retry: 0,
})

async function activate(provider: string, model: string): Promise<void> {
  await $fetch('/api/v1/admin/ai/configurations', {
    method: 'POST',
    body: { provider, model },
  })
  notice.value = '配置版本已激活。'
  await refresh()
}

async function saveSecret(provider: string, apiKey: string): Promise<void> {
  await $fetch(`/api/v1/admin/ai/providers/${provider}/secret`, {
    method: 'PUT',
    body: { api_key: apiKey },
  })
  notice.value = 'Secret 已写入私有存储，页面不会回显。'
  await refresh()
}
</script>

<template>
  <div>
    <p v-if="error" role="alert">AI 配置暂不可用，请检查权限与服务端状态。</p>
    <template v-else-if="data">
    <p v-if="notice" role="status">{{ notice }}</p>
    <AiConfigurationPanel
      :providers="data"
      @activate="activate"
      @save-secret="saveSecret"
    />
    </template>
    <p v-else role="status">正在加载 AI 配置…</p>
  </div>
</template>
