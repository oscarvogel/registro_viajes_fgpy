import { hasStoredSession } from '../services/session.js'
import { resolveLoginRedirect } from '../services/loginFlow.js'
import { isAdminSession } from '../services/adminAccess.js'

export const resolveAuthNavigation = (to, storage = globalThis.localStorage, adminUserIds) => {
  const hasSession = hasStoredSession(storage)

  if (to.meta?.requiresAuth && !hasSession) {
    return {
      path: '/login',
      query: { redirect: to.fullPath },
    }
  }

  if (to.meta?.requiresAdmin && !isAdminSession(storage, adminUserIds)) {
    return '/settings'
  }

  if (to.path === '/login' && hasSession) {
    return resolveLoginRedirect(to.query?.redirect, '/dashboard')
  }

  return true
}
