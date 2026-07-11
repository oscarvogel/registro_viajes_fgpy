import assert from 'node:assert/strict'
import test from 'node:test'
import {
  getPendingRecordEndpoint,
  preparePendingPayload,
  syncOnePendingRecord,
} from '../src/services/syncPendingRecord.js'

const createStorage = (user = { id: 123 }) => ({
  getItem: (key) => key === 'user' ? JSON.stringify(user) : null,
})

test('getPendingRecordEndpoint selects viaje and carreton endpoints', () => {
  assert.equal(getPendingRecordEndpoint('viaje'), '/registro-viaje')
  assert.equal(getPendingRecordEndpoint('carreton'), '/movimiento-carreton')
})

test('preparePendingPayload removes local fields, normalizes numbers and resolves usuario', () => {
  const result = preparePendingPayload({
    local_id: 1,
    synced: false,
    timestamp: 'now',
    record_type: 'carreton',
    blocked: true,
    blocked_reason: 'old',
    km_inicial: '10',
    km_final: '20',
    equipo_id: '5',
    unidad_negocio_id: '7',
    origen_carreton: null,
    destino_carreton: undefined,
  }, { storage: createStorage({ id: 321 }) })

  assert.equal(result.recordType, 'carreton')
  assert.equal(result.endpoint, '/movimiento-carreton')
  assert.deepEqual(result.payload, {
    km_inicial: 10,
    km_final: 20,
    equipo_id: 5,
    unidad_negocio_id: 7,
    origen_carreton: '',
    destino_carreton: '',
    usuario: 321,
  })
})

test('syncOnePendingRecord posts viaje payload to registro-viaje', async () => {
  const calls = []
  const result = await syncOnePendingRecord({
    record: { local_id: 1, record_type: 'viaje', chofer_id: 123, neto_origen: '10', neto_destino: '9' },
    apiUrl: '/api',
    storage: createStorage(),
    httpClient: {
      post: async (url, payload) => {
        calls.push({ url, payload })
        return { status: 200, data: { id: 99 } }
      },
    },
  })

  assert.equal(result.ok, true)
  assert.equal(result.endpoint, '/registro-viaje')
  assert.equal(calls[0].url, '/api/registro-viaje')
  assert.equal(calls[0].payload.neto_origen, 10)
  assert.equal(calls[0].payload.usuario, 123)
})

test('syncOnePendingRecord posts carreton payload to movimiento-carreton', async () => {
  const calls = []
  const result = await syncOnePendingRecord({
    record: { local_id: 2, record_type: 'carreton', usuario: 123, km_inicial: '1', km_final: '2' },
    apiUrl: '/api',
    httpClient: {
      post: async (url, payload) => {
        calls.push({ url, payload })
        return { status: 200, data: { id: 100 } }
      },
    },
  })

  assert.equal(result.ok, true)
  assert.equal(result.endpoint, '/movimiento-carreton')
  assert.equal(calls[0].url, '/api/movimiento-carreton')
  assert.equal(calls[0].payload.km_final, 2)
})

test('syncOnePendingRecord marks missing usuario as blocked without posting', async () => {
  let called = false
  const result = await syncOnePendingRecord({
    record: { local_id: 1, record_type: 'viaje' },
    apiUrl: '/api',
    storage: createStorage(null),
    httpClient: {
      post: async () => {
        called = true
      },
    },
  })

  assert.equal(called, false)
  assert.equal(result.ok, false)
  assert.equal(result.blocked, true)
  assert.equal(result.authRequired, false)
})

test('syncOnePendingRecord reports authRequired on 401 and keeps record retryable', async () => {
  const result = await syncOnePendingRecord({
    record: { local_id: 1, record_type: 'viaje', usuario: 123 },
    apiUrl: '/api',
    httpClient: {
      post: async () => {
        throw { response: { status: 401, data: { detail: 'No autenticado' } } }
      },
    },
  })

  assert.equal(result.ok, false)
  assert.equal(result.status, 401)
  assert.equal(result.authRequired, true)
  assert.equal(result.blocked, false)
  assert.equal(result.detail, 'No autenticado')
})

test('syncOnePendingRecord blocks carreton validation errors but not network errors', async () => {
  const validation = await syncOnePendingRecord({
    record: { local_id: 1, record_type: 'carreton', usuario: 123 },
    apiUrl: '/api',
    httpClient: {
      post: async () => {
        throw { response: { status: 400, data: { detail: 'KM invalido' } } }
      },
    },
  })
  assert.equal(validation.blocked, true)
  assert.equal(validation.detail, 'KM invalido')

  const network = await syncOnePendingRecord({
    record: { local_id: 1, record_type: 'carreton', usuario: 123 },
    apiUrl: '/api',
    httpClient: {
      post: async () => {
        throw new Error('offline')
      },
    },
  })
  assert.equal(network.blocked, false)
  assert.equal(network.authRequired, false)
  assert.equal(network.detail, 'offline')
})
