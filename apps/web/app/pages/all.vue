<script setup lang="ts">
import IntelligenceFeedPage from '../components/IntelligenceFeedPage.vue'
import { emptyFeedPages } from '../feed-pages'

const page = emptyFeedPages.all
</script>

<template>
  <IntelligenceFeedPage v-bind="page" />
</template>
