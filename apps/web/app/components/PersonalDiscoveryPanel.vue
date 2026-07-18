<script setup lang="ts">
import type {
  DiscoveryDailyUsageView,
  DiscoverySettingView,
  DiscoveryTopicPatchRequest,
  DiscoveryTopicView,
} from '@srbg/contracts'

const { data: setting, refresh: refreshSetting } = await useFetch<DiscoverySettingView>(
  '/api/v1/source-discovery/settings',
  { server: false, retry: 0, timeout: 5_000 },
)
const { data: topics, refresh: refreshTopics } = await useFetch<DiscoveryTopicView[]>(
  '/api/v1/source-discovery/topics',
  { server: false, default: () => [], retry: 0, timeout: 5_000 },
)
const { data: usage } = await useFetch<DiscoveryDailyUsageView>(
  '/api/v1/source-discovery/usage',
  { server: false, retry: 0, timeout: 5_000 },
)

const busy = ref(false)
const editing = ref<string | null>(null)
const message = ref<string | null>(null)
const problem = ref<string | null>(null)
const retry = ref<(() => Promise<void>) | null>(null)
const form = reactive({ keywords: '', excludedTerms: '', focusRegions: '', enabled: true })

const baiduLabel = computed(() => {
  const labels: Record<string, string> = {
    DISABLED: '已关闭', KEY_MISSING: '缺少 Key（免费发现不受影响）',
    AVAILABLE: '可用', BUDGET_EXHAUSTED: '预算耗尽',
  }
  return labels[setting.value?.baidu_status ?? 'DISABLED']
})

function edit(topic: DiscoveryTopicView): void {
  editing.value = topic.id
  form.keywords = topic.keywords.join('，')
  form.excludedTerms = topic.excluded_terms.join('，')
  form.focusRegions = topic.focus_regions.join('，')
  form.enabled = topic.enabled
}

function values(value: string): string[] {
  return [...new Set(value.split(/[,，、\n]/).map(item => item.trim()).filter(Boolean))]
}

async function toggleDiscovery(): Promise<void> {
  if (!setting.value || busy.value) return
  busy.value = true
  problem.value = null
  try {
    await $fetch('/api/v1/source-discovery/settings', {
      method: 'PATCH', body: { automation_enabled: !setting.value.automation_enabled }, retry: 0, timeout: 5_000,
    })
    await refreshSetting()
    message.value = '自动发现设置已保存。'
  }
  catch {
    problem.value = '自动发现设置保存失败，原设置保持不变。'
    retry.value = toggleDiscovery
  }
  finally {
    busy.value = false
  }
}

async function saveTopic(topic: DiscoveryTopicView): Promise<void> {
  if (busy.value) return
  const keywords = values(form.keywords)
  if (!keywords.length) {
    message.value = '关键词不能为空。'
    return
  }
  busy.value = true
  problem.value = null
  const body: DiscoveryTopicPatchRequest = {
    keywords,
    excluded_terms: values(form.excludedTerms),
    focus_regions: values(form.focusRegions),
    enabled: form.enabled,
  }
  try {
    await $fetch(`/api/v1/source-discovery/topics/${topic.id}`, {
      method: 'PATCH', body, retry: 0, timeout: 5_000,
    })
    await refreshTopics()
    editing.value = null
    message.value = `${topic.name}主题已保存。`
  }
  catch {
    problem.value = `${topic.name}主题保存失败，原主题保持不变。`
    retry.value = () => saveTopic(topic)
  }
  finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="discovery-panel" aria-labelledby="discovery-panel-title">
    <div class="discovery-panel__heading">
      <div>
        <p class="discovery-panel__eyebrow">PERS-05</p>
        <h2 id="discovery-panel-title">自动发现</h2>
        <p>免费 RSS、Sitemap 和机构外链优先；外链只扩展一层。</p>
      </div>
      <button
        type="button"
        role="switch"
        :aria-checked="setting?.automation_enabled ?? false"
        :disabled="busy || !setting"
        @click="toggleDiscovery"
      >
        {{ setting?.automation_enabled ? '已开启' : '已关闭' }}
      </button>
    </div>

    <div class="discovery-panel__usage" aria-label="今日自动发现额度">
      <p><span>今日探测</span><strong>{{ usage?.probe_used ?? 0 }}/{{ usage?.probe_limit ?? 100 }}</strong></p>
      <p><span>今日自动启用</span><strong>{{ usage?.auto_enable_used ?? 0 }}/{{ usage?.auto_enable_limit ?? 20 }}</strong></p>
      <p><span>百度搜索</span><strong>{{ baiduLabel }}</strong></p>
      <p><span>下次运行</span><strong>{{ setting?.next_run_at ? new Date(setting.next_run_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '等待调度' }}</strong></p>
    </div>

    <p v-if="message" role="status" class="discovery-panel__message">{{ message }}</p>
    <p v-if="problem" role="alert" class="discovery-panel__problem">
      {{ problem }} <button v-if="retry" type="button" @click="retry()">重试</button>
    </p>
    <div class="discovery-panel__topics">
      <article v-for="topic in topics" :key="topic.id" class="discovery-topic">
        <div class="discovery-topic__title">
          <div><h3>{{ topic.name }}</h3><p>{{ topic.keywords.join('、') }}</p></div>
          <button type="button" @click="edit(topic)">编辑主题</button>
        </div>
        <form v-if="editing === topic.id" @submit.prevent="saveTopic(topic)">
          <label>关键词<input v-model="form.keywords" required></label>
          <label>排除词<input v-model="form.excludedTerms"></label>
          <label>重点地区<input v-model="form.focusRegions"></label>
          <label class="discovery-topic__check"><input v-model="form.enabled" type="checkbox">启用主题</label>
          <div><button type="submit" :disabled="busy">{{ busy ? '正在保存…' : '保存' }}</button><button type="button" @click="editing = null">取消</button></div>
        </form>
      </article>
    </div>
  </section>
</template>

<style scoped>
.discovery-panel { margin: 1rem 0; padding: 1rem; border: 1px solid var(--ui-border); border-radius: .75rem; background: var(--ui-bg); }
.discovery-panel__heading, .discovery-topic__title { display: flex; align-items: start; justify-content: space-between; gap: 1rem; }
.discovery-panel__eyebrow { margin: 0; color: var(--color-ink-900); font-size: .75rem; font-weight: 700; }
.discovery-panel__usage { display: grid; grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); gap: .75rem; margin: 1rem 0; }
.discovery-panel__usage p { display: grid; gap: .25rem; margin: 0; padding: .75rem; border-radius: .5rem; background: var(--ui-bg-muted); }
.discovery-panel__topics { display: grid; gap: .75rem; }
.discovery-topic { padding: .75rem; border: 1px solid var(--ui-border); border-radius: .5rem; }
.discovery-topic h3, .discovery-topic p { margin: 0; }
.discovery-topic form { display: grid; gap: .65rem; margin-top: .75rem; }
.discovery-topic label:not(.discovery-topic__check) { display: grid; gap: .25rem; }
.discovery-topic input:not([type='checkbox']) { min-height: 2.5rem; padding: .5rem; border: 1px solid var(--ui-border); border-radius: .4rem; }
.discovery-topic__check { display: flex; gap: .5rem; align-items: center; }
.discovery-panel__message { color: var(--ui-primary); }
.discovery-panel__problem { color: var(--color-conflict-700); }
</style>
