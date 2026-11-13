// Navigation only: the backend must still enforce identity and resource ownership.
// role_codes is returned by userinfo; absent/invalid codes grant no business entry.
export const BUSINESS_HOMES = {
  STUDENT: '/student/classroom',
  TEACHER: '/teacher/classroom',
}

export function isAdministrator(user = {}) {
  return user.is_admin === true || user.is_superuser === true
}

export function getBusinessRoles(user = {}) {
  if (isAdministrator(user)) return []
  if (!Array.isArray(user.role_codes)) return []
  return [
    ...new Set(
      user.role_codes.filter(
        (code) => typeof code === 'string' && Object.hasOwn(BUSINESS_HOMES, code)
      )
    ),
  ]
}

export function getDefaultPath(user = {}, activeRole = '') {
  if (isAdministrator(user)) return '/classroom/dashboard'
  if (getBusinessRoles(user).includes(activeRole)) return BUSINESS_HOMES[activeRole]
  const firstRole = getBusinessRoles(user)[0]
  return firstRole ? BUSINESS_HOMES[firstRole] : '/account'
}

export function getRouteBusinessRole(route) {
  return (
    route.meta?.businessRole ||
    Object.keys(BUSINESS_HOMES).find(
      (code) =>
        route.path === '/' + code.toLowerCase() ||
        route.path?.startsWith('/' + code.toLowerCase() + '/')
    )
  )
}

export function canAccessBusinessRoute(route, user = {}) {
  const role = getRouteBusinessRole(route)
  return !role || getBusinessRoles(user).includes(role)
}

export function getSafeRedirect(value, router, user) {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return null
  // Reject encoded path separators, backslashes and control characters.
  if (/[\\\s]/.test(value) || /%(?:2f|5c|0[0-9a-f]|1[0-9a-f]|7f)/i.test(value)) return null
  const target = router.resolve(value)
  if (['/login', '/register', '/403', '/404'].includes(target.path)) return null
  if (
    !target.matched.length ||
    target.matched.some((item) => ['Empty', 'NotFound'].includes(item.name))
  )
    return null
  if (!target.matched.every((item) => canAccessBusinessRoute(item, user))) return null
  return target.fullPath
}

export function filterBusinessMenus(routes, user, parentPath = '') {
  return routes.flatMap((route) => {
    const path = route.path.startsWith('/')
      ? route.path
      : parentPath.replace(/\/$/, '') + '/' + route.path
    if (!canAccessBusinessRoute({ ...route, path }, user)) return []
    if (!route.children) return [route]
    const children = filterBusinessMenus(route.children, user, path)
    return children.length ? [{ ...route, children }] : []
  })
}
