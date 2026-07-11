import assert from 'node:assert/strict'
import test from 'node:test'
import {
  FUEL_REMITO_MAX_LENGTH,
  buildCarretonPayload,
  buildFuelLastKmParams,
  buildFuelPayload,
  buildHistoryRequests,
  findEquipoByPatente,
  findUnidadById,
  getLastFuelKmHora,
  getPendingCarretonLastKm,
  getStoredUserId,
  normalizeKilometraje,
  normalizeFuelRemito,
  normalizeApiList,
} from '../src/services/criticalScreens.js'

const createStorage = (user) => ({
  getItem: (key) => key === 'user' && user ? JSON.stringify(user) : null,
})

test('history requests use logged user id as chofer_id for both protected endpoints', () => {
  const requests = buildHistoryRequests({
    apiUrl: '/api',
    userId: 123,
    fechaDesde: '2026-01-01',
    fechaHasta: '2026-01-31',
  })

  assert.deepEqual(requests, [
    {
      url: '/api/historial-viajes',
      params: { chofer_id: 123, fecha_desde: '2026-01-01', fecha_hasta: '2026-01-31' },
    },
    {
      url: '/api/movimientos-carreton',
      params: { chofer_id: 123, fecha_desde: '2026-01-01', fecha_hasta: '2026-01-31' },
    },
  ])
})

test('getStoredUserId reads logged user id from storage', () => {
  assert.equal(getStoredUserId(createStorage({ id: 77 })), 77)
  assert.equal(getStoredUserId(createStorage(null)), null)
})

test('normalizeApiList supports array and paged shapes', () => {
  assert.deepEqual(normalizeApiList([{ id: 1 }]), [{ id: 1 }])
  assert.deepEqual(normalizeApiList({ items: [{ id: 2 }] }), [{ id: 2 }])
  assert.deepEqual(normalizeApiList(null), [])
})

test('fuel last km params query last two years for selected equipo', () => {
  const params = buildFuelLastKmParams({
    equipoId: 5,
    now: new Date('2026-05-24T12:00:00Z'),
  })

  assert.deepEqual(params, {
    fecha_desde: '2024-05-24',
    fecha_hasta: '2026-05-24',
    equipo_id: 5,
  })
})

test('fuel payload includes logged user and numeric fields', () => {
  const payload = buildFuelPayload({
    userId: 123,
    form: {
      fecha_carga: '2026-05-24',
      litros: '10.5',
      km_hora: '100',
      equipo_id: '7',
      paniol_id: '3',
      remito: 'R001',
      observaciones: 'ok',
    },
  })

  assert.deepEqual(payload, {
    fecha_carga: '2026-05-24',
    litros: 10.5,
    km_hora: 100,
    equipo_id: 7,
    paniol_id: 3,
    remito: 'R001',
    observaciones: 'ok',
    usuario: '123',
  })
})

test('fuel remito is trimmed and capped to backend length', () => {
  assert.equal(FUEL_REMITO_MAX_LENGTH, 12)
  assert.equal(normalizeFuelRemito('  ABCDEFGHIJKLM  '), 'ABCDEFGHIJKL')

  const payload = buildFuelPayload({
    userId: 123,
    form: {
      fecha_carga: '2026-05-24',
      litros: '10.5',
      km_hora: '100',
      equipo_id: '7',
      paniol_id: '3',
      remito: '  ABCDEFGHIJKLM  ',
      observaciones: 'ok',
    },
  })

  assert.equal(payload.remito, 'ABCDEFGHIJKL')
})

test('fuel helpers extract last km hora from ordered API results', () => {
  assert.equal(getLastFuelKmHora([{ km_hora: '10' }, { km_hora: '25.5' }]), 25.5)
  assert.equal(getLastFuelKmHora([]), null)
})

test('carreton defaults find equipo by normalized patente and unidad by id', () => {
  assert.deepEqual(findEquipoByPatente([{ id: 1, patente: 'ABC 123' }], 'abc123'), { id: 1, patente: 'ABC 123' })
  assert.deepEqual(findUnidadById([{ id: 7, descripcion: 'UN' }], '7'), { id: 7, descripcion: 'UN' })
})

test('carreton pending last km uses latest local record for selected equipo', () => {
  const pending = [
    { local_id: 1, record_type: 'carreton', equipo_id: 5, km_final: '100' },
    { local_id: 3, record_type: 'carreton', equipo_id: 5, km_final: '130' },
    { local_id: 2, record_type: 'viaje', equipo_id: 5, km_final: '999' },
  ]

  assert.equal(getPendingCarretonLastKm(pending, 5), 130)
  assert.equal(getPendingCarretonLastKm(pending, 99), null)
})

test('kilometraje normalizer accepts local thousands format and decimal values', () => {
  assert.equal(normalizeKilometraje('99.624'), 99624)
  assert.equal(normalizeKilometraje('1.234.567'), 1234567)
  assert.equal(normalizeKilometraje('123.45'), 123.45)
  assert.equal(normalizeKilometraje('123,45'), 123.45)
  assert.equal(normalizeKilometraje('99.624,50'), 99624.5)
})

test('carreton payload trims text, includes logged user and numeric fields', () => {
  const payload = buildCarretonPayload({
    userId: 123,
    form: {
      fecha: '2026-05-24',
      equipo_id: '5',
      unidad_negocio_id: '7',
      hora_inicio_viaje: '',
      km_inicial: '100',
      km_final: '120',
      estado_carga: 'cargado',
      tipo_maquina_transportada: ' Excavadora ',
      origen_carreton: ' Origen ',
      destino_carreton: ' Destino ',
    },
  })

  assert.deepEqual(payload, {
    fecha: '2026-05-24',
    equipo_id: 5,
    unidad_negocio_id: 7,
    hora_inicio_viaje: null,
    km_inicial: 100,
    km_final: 120,
    estado_carga: 'cargado',
    tipo_maquina_transportada: 'Excavadora',
    origen_carreton: 'Origen',
    destino_carreton: 'Destino',
    usuario: '123',
  })
})

test('carreton payload converts Paraguayan thousands separators before syncing', () => {
  const payload = buildCarretonPayload({
    userId: 55,
    form: {
      fecha: '2026-05-18',
      equipo_id: '10',
      unidad_negocio_id: '11',
      hora_inicio_viaje: '05:55',
      km_inicial: '99.624',
      km_final: '99.635',
      estado_carga: 'cargado',
      tipo_maquina_transportada: ' movimiento compactador ',
      origen_carreton: ' Playa Biomasa ',
      destino_carreton: ' Porteria Paraguari ',
    },
  })

  assert.equal(payload.km_inicial, 99624)
  assert.equal(payload.km_final, 99635)
  assert.equal(payload.usuario, '55')
})
