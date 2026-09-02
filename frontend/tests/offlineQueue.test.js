import assert from 'node:assert/strict'
import test from 'node:test'
import {
  OFFLINE_STATUS,
  buildOfflineOperation,
  enqueueOperation,
  getAllOperations,
  getPendingCount,
  getPendingOperations,
  markError,
  markSynced,
  markSyncing,
  removeSynced,
  retryOperation,
} from '../src/services/offlineQueue.js'

class MemoryDb {
  constructor() {
    this.records = new Map()
  }
  async put(_store, value) {
    this.records.set(value.client_uuid, structuredClone(value))
    return value.client_uuid
  }
  async get(_store, key) {
    const value = this.records.get(key)
    return value ? structuredClone(value) : undefined
  }
  async getAll() {
    return [...this.records.values()].map((item) => structuredClone(item))
  }
  async delete(_store, key) {
    this.records.delete(key)
  }
}

test('buildOfflineOperation creates a stable pending envelope without mutating payload', () => {
  const payload = { equipo_id: 12, nested: { value: 1 } }
  const operation = buildOfflineOperation('viaje', payload, {
    clientUuid: 'uuid-1',
    createdAt: '2026-09-02T12:00:00.000Z',
  })

  payload.nested.value = 99
  assert.equal(operation.client_uuid, 'uuid-1')
  assert.equal(operation.entity_type, 'viaje')
  assert.equal(operation.status, OFFLINE_STATUS.PENDING)
  assert.equal(operation.retry_count, 0)
  assert.equal(operation.payload.nested.value, 1)
})

test('enqueueOperation persists records and pending queries include pending and error', async () => {
  const db = new MemoryDb()
  await enqueueOperation('viaje', { a: 1 }, { db, clientUuid: 'a', createdAt: '2026-09-02T10:00:00Z' })
  await enqueueOperation('combustible', { b: 2 }, { db, clientUuid: 'b', createdAt: '2026-09-02T11:00:00Z' })

  await markError('b', new Error('offline'), { db, at: '2026-09-02T11:01:00Z' })

  assert.equal(await getPendingCount({ db }), 2)
  assert.deepEqual((await getPendingOperations({ db })).map((item) => item.client_uuid), ['a', 'b'])
  assert.deepEqual((await getAllOperations({ db })).map((item) => item.client_uuid), ['a', 'b'])
})

test('sync lifecycle keeps payload and server reference', async () => {
  const db = new MemoryDb()
  await enqueueOperation('viaje', { remito: '123' }, { db, clientUuid: 'uuid-sync' })

  const syncing = await markSyncing('uuid-sync', { db, at: '2026-09-02T12:01:00Z' })
  assert.equal(syncing.status, OFFLINE_STATUS.SYNCING)

  const synced = await markSynced('uuid-sync', 456, { db, at: '2026-09-02T12:02:00Z' })
  assert.equal(synced.status, OFFLINE_STATUS.SYNCED)
  assert.equal(synced.server_id, 456)
  assert.deepEqual(synced.payload, { remito: '123' })
  assert.equal(await getPendingCount({ db }), 0)
})

test('errors increment retry count and retry returns operation to pending', async () => {
  const db = new MemoryDb()
  await enqueueOperation('combustible', { litros: 100 }, { db, clientUuid: 'uuid-error' })

  let record = await markError('uuid-error', { response: { data: { detail: 'Servidor no disponible' } } }, { db })
  assert.equal(record.retry_count, 1)
  assert.equal(record.last_error, 'Servidor no disponible')

  record = await markError('uuid-error', new Error('offline'), { db })
  assert.equal(record.retry_count, 2)
  assert.equal(record.last_error, 'offline')

  record = await retryOperation('uuid-error', { db })
  assert.equal(record.status, OFFLINE_STATUS.PENDING)
  assert.equal(record.last_error, null)
  assert.equal(record.retry_count, 2)
})

test('removeSynced refuses to delete unsynchronized data', async () => {
  const db = new MemoryDb()
  await enqueueOperation('viaje', { a: 1 }, { db, clientUuid: 'keep-me' })

  await assert.rejects(() => removeSynced('keep-me', { db }), /aun no esta sincronizada/)
  assert.equal(await getPendingCount({ db }), 1)

  await markSynced('keep-me', 1, { db })
  assert.equal(await removeSynced('keep-me', { db }), true)
  assert.equal((await getAllOperations({ db })).length, 0)
})
