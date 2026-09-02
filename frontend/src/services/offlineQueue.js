export const OFFLINE_STATUS = Object.freeze({
  PENDING: 'PENDIENTE',
  SYNCING: 'SINCRONIZANDO',
  SYNCED: 'SINCRONIZADO',
  ERROR: 'ERROR',
})

const STORE_NAME = 'offlineOperations'

const nowIso = () => new Date().toISOString()

const defaultUuid = () => {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(16).slice(2)}-${Math.random().toString(16).slice(2)}`
}

const getDb = async (db) => {
  if (db) return db
  const module = await import('../db.js')
  return module.dbPromise
}

const sanitizeError = (error) => {
  if (!error) return null
  if (typeof error === 'string') return error.slice(0, 500)
  const detail = error?.response?.data?.detail || error?.message || String(error)
  return String(detail).slice(0, 500)
}

export const buildOfflineOperation = (entityType, payload, options = {}) => {
  if (!entityType || typeof entityType !== 'string') {
    throw new TypeError('entityType es obligatorio')
  }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new TypeError('payload debe ser un objeto')
  }

  const createdAt = options.createdAt || nowIso()
  return {
    client_uuid: options.clientUuid || defaultUuid(),
    entity_type: entityType,
    payload: structuredClone(payload),
    created_at_local: createdAt,
    status: OFFLINE_STATUS.PENDING,
    retry_count: 0,
    last_attempt_at: null,
    last_error: null,
    server_id: null,
    synced_at: null,
  }
}

export async function enqueueOperation(entityType, payload, options = {}) {
  const operation = buildOfflineOperation(entityType, payload, options)
  const db = await getDb(options.db)
  await db.put(STORE_NAME, operation)
  return operation
}

export async function getOperation(clientUuid, options = {}) {
  const db = await getDb(options.db)
  return db.get(STORE_NAME, clientUuid)
}

export async function getAllOperations(options = {}) {
  const db = await getDb(options.db)
  const records = await db.getAll(STORE_NAME)
  return records.sort((a, b) => String(a.created_at_local).localeCompare(String(b.created_at_local)))
}

export async function getPendingOperations(options = {}) {
  const records = await getAllOperations(options)
  return records.filter((item) => [OFFLINE_STATUS.PENDING, OFFLINE_STATUS.ERROR].includes(item.status))
}

export async function getPendingCount(options = {}) {
  return (await getPendingOperations(options)).length
}

async function updateOperation(clientUuid, changes, options = {}) {
  const db = await getDb(options.db)
  const current = await db.get(STORE_NAME, clientUuid)
  if (!current) throw new Error(`Operacion offline inexistente: ${clientUuid}`)
  const updated = { ...current, ...changes }
  await db.put(STORE_NAME, updated)
  return updated
}

export function markSyncing(clientUuid, options = {}) {
  return updateOperation(clientUuid, {
    status: OFFLINE_STATUS.SYNCING,
    last_attempt_at: options.at || nowIso(),
    last_error: null,
  }, options)
}

export async function markSynced(clientUuid, serverId, options = {}) {
  return updateOperation(clientUuid, {
    status: OFFLINE_STATUS.SYNCED,
    server_id: serverId ?? null,
    synced_at: options.at || nowIso(),
    last_error: null,
  }, options)
}

export async function markError(clientUuid, error, options = {}) {
  const current = await getOperation(clientUuid, options)
  if (!current) throw new Error(`Operacion offline inexistente: ${clientUuid}`)
  return updateOperation(clientUuid, {
    status: OFFLINE_STATUS.ERROR,
    retry_count: Number(current.retry_count || 0) + 1,
    last_attempt_at: options.at || nowIso(),
    last_error: sanitizeError(error),
  }, options)
}

export function retryOperation(clientUuid, options = {}) {
  return updateOperation(clientUuid, {
    status: OFFLINE_STATUS.PENDING,
    last_error: null,
  }, options)
}

export async function removeSynced(clientUuid, options = {}) {
  const db = await getDb(options.db)
  const current = await db.get(STORE_NAME, clientUuid)
  if (!current) return false
  if (current.status !== OFFLINE_STATUS.SYNCED) {
    throw new Error('No se puede eliminar una operacion que aun no esta sincronizada')
  }
  await db.delete(STORE_NAME, clientUuid)
  return true
}
