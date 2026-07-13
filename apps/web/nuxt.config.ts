export default defineNuxtConfig({
  app: {
    head: {
      htmlAttrs: { lang: 'zh-CN' },
      meta: [
        { name: 'description', content: '四川路桥行业数智与安全情报平台演示环境' },
        { name: 'color-scheme', content: 'light' },
      ],
      title: '四川路桥·智安情报',
    },
  },
  compatibilityDate: '2026-07-13',
  css: ['~/assets/css/main.css'],
  devtools: { enabled: false },
  modules: ['@nuxt/ui', '@nuxt/eslint'],
  routeRules: {
    '/**': {
      headers: {
        'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' http://127.0.0.1:8000 http://localhost:8000",
        'Referrer-Policy': 'no-referrer',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
      },
    },
  },
  runtimeConfig: {
    internalApiBase: 'http://api:8000',
  },
  typescript: {
    strict: true,
    typeCheck: true,
  },
})
