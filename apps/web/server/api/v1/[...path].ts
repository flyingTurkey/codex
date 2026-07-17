import { getProxyRequestHeaders, getRequestURL, getRouterParam, proxyRequest } from 'h3'

export default defineEventHandler(async (event) => {
  const path = getRouterParam(event, 'path')
  if (!path) {
    throw createError({ statusCode: 404, statusMessage: 'API path is required' })
  }
  const config = useRuntimeConfig(event)
  const headers = new Headers(getProxyRequestHeaders(event))
  headers.delete('x-srbg-local-roles')
  headers.delete('x-srbg-local-user')
  headers.delete('x-srbg-local-user-id')
  headers.delete('x-srbg-local-step-up')
  const localEnvironment = process.env.SRBG_ENVIRONMENT?.toLowerCase()
  const localIdentityEnabled = localEnvironment
    ? ['development', 'test', 'demo'].includes(localEnvironment)
    : import.meta.dev || process.env.NODE_ENV === 'test'
  if (localIdentityEnabled) {
    const compatibleRoles = config.localAppRoles
      .split(',')
      .map(role => role.trim())
      .filter(Boolean)
    headers.set('x-srbg-local-roles', [...new Set(['owner', ...compatibleRoles])].join(','))
    headers.set('x-srbg-local-user', 'Local Personal Owner')
    headers.set('x-srbg-local-step-up', 'true')
  }

  const search = getRequestURL(event).search
  return proxyRequest(event, `${config.internalApiBase}/api/v1/${path}${search}`, {
    headers,
    streamRequest: true,
  })
})
