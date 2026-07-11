import { ADMIN_USER_IDS } from '../config.js'
import { getStoredSession } from './session.js'

export const isAdminUserId = (userId, adminUserIds = ADMIN_USER_IDS) => {
  const numericId = Number(userId)
  return Number.isInteger(numericId) && adminUserIds.includes(numericId)
}

export const isAdminSession = (storage = globalThis.localStorage, adminUserIds = ADMIN_USER_IDS) => {
  const session = getStoredSession(storage)
  return Boolean(session && isAdminUserId(session.user.id, adminUserIds))
}
