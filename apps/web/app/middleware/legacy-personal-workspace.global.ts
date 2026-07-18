const legacySourcePrefixes = [
  '/admin/sources',
  '/admin/source-health',
  '/admin/review',
]
const legacyWorkspaceRoutes = new Set(['/admin/clusters', '/admin/pilot'])

export default defineNuxtRouteMiddleware((to) => {
  const legacy = legacyWorkspaceRoutes.has(to.path)
    || legacySourcePrefixes.some(prefix => to.path === prefix || to.path.startsWith(`${prefix}/`))
  if (!legacy) return
  return navigateTo(
    { path: '/sources', query: { migrated: 'legacy-source-management' } },
    { replace: true },
  )
})
