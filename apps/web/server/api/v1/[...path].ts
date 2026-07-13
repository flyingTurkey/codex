import { getProxyRequestHeaders, getRouterParam, proxyRequest } from 'h3'

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
  headers.set('x-srbg-local-roles', config.localSourceRoles)
  headers.set('x-srbg-local-user', 'Local Source Admin')

  return proxyRequest(event, `${config.internalApiBase}/api/v1/${path}`, {
    headers,
    streamRequest: true,
  })
})
