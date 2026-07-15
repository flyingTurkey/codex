<script setup lang="ts">
const route = useRoute()
const itemId = String(route.params.id)
const response = await $fetch.raw(`/api/v1/items/${itemId}`, { retry: 0, timeout: 5_000 })
const successor = response.headers
  .get('link')
  ?.match(/<(?<path>\/api\/v1\/events\/[0-9a-f-]+)>; rel="successor-version"/i)
  ?.groups?.path

if (!successor) {
  throw createError({ statusCode: 409, statusMessage: 'Item 尚未建立稳定 Event 身份' })
}

await navigateTo(successor.replace('/api/v1', ''), { redirectCode: 308, replace: true })
</script>
