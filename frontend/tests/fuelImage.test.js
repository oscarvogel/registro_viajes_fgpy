import assert from 'node:assert/strict'
import test from 'node:test'
import {
  FUEL_TIPO_REMITO_INTERNO,
  FUEL_TIPO_TICKET,
  analyzeFuelImage,
  confirmFuelRemitoInternoImage,
  confirmFuelTicketImage,
  createFuelImageObjectUrl,
  fetchFuelImageBlob,
  fuelImageUrl,
  mapFuelImageError,
  prepareFuelImageForUpload,
  revokeFuelImageObjectUrl,
  validateFuelImageFile,
} from '../src/services/fuelImage.js'
import {
  buildConfirmPayload,
  createReviewModel,
  readFuelImageSettings,
  transitionReviewState,
} from '../src/services/fuelImageReview.js'

const file = () => new Blob(['image'], { type: 'image/jpeg' })

test('analyzeFuelImage posts file + tipo and returns response data', async () => {
  let request
  const http = { post: async (...args) => { request = args; return { data: { upload_token: 'tok', tipo: FUEL_TIPO_TICKET, proposal: {} } } } }
  const image = file()
  const result = await analyzeFuelImage(image, FUEL_TIPO_TICKET, http, 'https://api.test')
  assert.equal(request[0], 'https://api.test/fuel-image/analyze')
  assert.equal(request[1].get('file').size, image.size)
  assert.equal(request[1].get('file').type, image.type)
  assert.equal(request[1].get('tipo'), FUEL_TIPO_TICKET)
  assert.deepEqual(result.tipo, FUEL_TIPO_TICKET)
})

test('analyzeFuelImage rejects invalid tipo before HTTP', async () => {
  let calls = 0
  const http = { post: async () => { calls += 1 } }
  await assert.rejects(() => analyzeFuelImage(file(), 'otro', http), /Tipo/i)
  await assert.rejects(() => analyzeFuelImage(file(), null, http), /Tipo/i)
  assert.equal(calls, 0)
})

test('analyzeFuelImage rejects non-Blob input before HTTP', async () => {
  let calls = 0
  const http = { post: async () => { calls += 1 } }
  await assert.rejects(() => analyzeFuelImage(null, FUEL_TIPO_TICKET, http), /imagen/i)
  await assert.rejects(() => analyzeFuelImage({ name: 'x.jpg' }, FUEL_TIPO_TICKET, http), /imagen/i)
  assert.equal(calls, 0)
})

test('confirmFuelTicketImage and confirmFuelRemitoInternoImage hit the right endpoints', async () => {
  const tCalls = []
  const rCalls = []
  const tHttp = { post: async (...args) => { tCalls.push(args); return { data: { movimiento_id: 1, imagen_id: 11 } } } }
  const rHttp = { post: async (...args) => { rCalls.push(args); return { data: { movimiento_id: 2, imagen_id: 22 } } } }
  const payload = { upload_token: 'tok' }
  assert.deepEqual(await confirmFuelTicketImage(payload, tHttp, '/api'), { movimiento_id: 1, imagen_id: 11 })
  assert.deepEqual(await confirmFuelRemitoInternoImage(payload, rHttp, '/api'), { movimiento_id: 2, imagen_id: 22 })
  assert.equal(tCalls[0][0], '/api/fuel-image/confirm/ticket')
  assert.equal(rCalls[0][0], '/api/fuel-image/confirm/remito-interno')
})

test('fuelImageUrl validates and encodes id', () => {
  assert.equal(fuelImageUrl(12, '/api'), '/api/fuel-image/12/blob')
  for (const id of [0, -1, 1.2, '1', '../secret']) assert.throws(() => fuelImageUrl(id, '/api'), /id/i)
})

test('fetchFuelImageBlob uses authenticated injected GET and validates image Blob', async () => {
  const blob = new Blob(['image'], { type: 'image/jpeg' })
  let request
  const http = { get: async (...args) => { request = args; return { data: blob } } }
  assert.equal(await fetchFuelImageBlob(12, http, '/api'), blob)
  assert.deepEqual(request, ['/api/fuel-image/12/blob', { responseType: 'blob' }])
  await assert.rejects(() => fetchFuelImageBlob(12, { get: async () => ({ data: new Blob(['x'], { type: 'text/html' }) }) }, '/api'), /imagen/i)
})

test('image object URL helpers inject lifecycle API and reject non-image data', () => {
  const blob = new Blob(['image'], { type: 'image/png' })
  const calls = []
  const urlApi = { createObjectURL: (value) => { calls.push(['create', value]); return 'blob:safe' }, revokeObjectURL: (url) => calls.push(['revoke', url]) }
  assert.equal(createFuelImageObjectUrl(blob, urlApi), 'blob:safe')
  revokeFuelImageObjectUrl('blob:safe', urlApi)
  assert.deepEqual(calls, [['create', blob], ['revoke', 'blob:safe']])
  assert.throws(() => createFuelImageObjectUrl(new Blob(['x'], { type: '' }), urlApi), /imagen/i)
})

test('mapFuelImageError returns safe Spanish actions without reflecting backend details', () => {
  const expected = {
    400: ['La solicitud de imagen no es válida.', false], 401: ['Tu sesión venció. Iniciá sesión nuevamente.', false],
    403: ['No tenés permiso para cargar esta imagen.', false], 409: ['Este comprobante ya fue confirmado.', false],
    410: ['La imagen venció. Volvé a analizarla.', true], 413: ['La imagen es demasiado grande.', false],
    422: ['Revisá los datos detectados antes de confirmar.', false], 502: ['El servicio de lectura no está disponible.', true],
    503: ['El servicio de lectura no está disponible.', true], 504: ['El servicio tardó demasiado en responder.', true],
  }
  for (const [status, [message, retry]] of Object.entries(expected)) {
    const error = { response: { status: Number(status) } }
    const mapped = mapFuelImageError(error)
    assert.equal(mapped.message, message, `status ${status} message`)
    assert.equal(mapped.retry, retry, `status ${status} retry`)
  }
  const fallback = mapFuelImageError({ response: { status: 418 } })
  assert.equal(fallback.retry, true)
})

test('validateFuelImageFile rejects empty and unsupported', () => {
  assert.throws(() => validateFuelImageFile(null), /imagen/i)
  assert.throws(() => validateFuelImageFile(new Blob(['x'], { type: 'text/plain' })), /JPG/i)
  assert.throws(() => validateFuelImageFile(new Blob([''], { type: 'image/jpeg' })), /vacía/i)
  // 11 MB blob
  const big = new Blob([new Uint8Array(11 * 1024 * 1024)], { type: 'image/jpeg' })
  assert.throws(() => validateFuelImageFile(big, 10 * 1024 * 1024), /demasiado grande/i)
  const f = file()
  const ok = validateFuelImageFile(f)
  assert.ok(ok instanceof Blob)
  assert.equal(ok.size, f.size)
  assert.equal(ok.type, f.type)
})

test('prepareFuelImageForUpload returns input when under maxBytes and rejects oversized without imageApi', async () => {
  const small = file()
  assert.equal(await prepareFuelImageForUpload(small), small)
  const big = new Blob([new Uint8Array(11 * 1024 * 1024)], { type: 'image/jpeg' })
  await assert.rejects(
    () => prepareFuelImageForUpload(big, { imageApi: { createImageBitmap: undefined, createCanvas: () => null } }),
    /demasiado grande|no pudo/i
  )
})

// --- fuelImageReview tests ---

const baseSettings = () => ({
  userId: 1, user: { id: 1, nombre: 'Chofer', apellido: 'Test', activo: true },
  patente: 'AAXO300', equipoId: 4, equipo: { id: 4, patente: 'AAXO300', descripcion: 'Scania', activo: true },
  unidadNegocioId: 1, unidadNegocio: { id: 1, descripcion: 'Forestal', prefijo: 'F', activo: true },
  internoId: 29, internoNombre: 'INTERNO FORESTAL PARAGUAY',
  activeProviderIds: [2, 3, 29],
  missing: [], errors: [], complete: true,
})

test('readFuelImageSettings resolves INTERNO by name from proveedores', () => {
  const catalog = {
    empleados: [{ id: 1, nombre: 'Chofer', apellido: 'Test', activo: true }],
    equipos: [{ id: 4, patente: 'AAXO300', descripcion: 'Scania', activo: true }],
    unidadesNegocio: [{ id: 1, descripcion: 'Forestal', prefijo: 'F', activo: true }],
    proveedores: [
      { id: 1, razon_social: 'PROVEEDOR GENERICO', activo: true },
      { id: 29, razon_social: 'INTERNO FORESTAL PARAGUAY', activo: true },
    ],
  }
  const storage = {
    getItem: (key) => {
      if (key === 'user') return JSON.stringify({ id: 1 })
      if (key === 'default_patente') return 'AAXO300'
      if (key === 'default_unidad_negocio') return '1'
      return null
    },
  }
  const settings = readFuelImageSettings({ storage, catalog })
  assert.equal(settings.internoId, 29)
  assert.equal(settings.internoNombre, 'INTERNO FORESTAL PARAGUAY')
  assert.equal(settings.equipoId, 4)
  assert.equal(settings.complete, true)
})

test('readFuelImageSettings reports missing INTERNO without blocking settings complete', () => {
  const catalog = {
    empleados: [{ id: 1, nombre: 'Chofer', apellido: 'Test', activo: true }],
    equipos: [{ id: 4, patente: 'AAXO300', descripcion: 'Scania', activo: true }],
    unidadesNegocio: [{ id: 1, descripcion: 'Forestal', prefijo: 'F', activo: true }],
    proveedores: [{ id: 1, razon_social: 'PROVEEDOR GENERICO', activo: true }],
  }
  const storage = {
    getItem: (key) => {
      if (key === 'user') return JSON.stringify({ id: 1 })
      if (key === 'default_patente') return 'AAXO300'
      if (key === 'default_unidad_negocio') return '1'
      return null
    },
  }
  const settings = readFuelImageSettings({ storage, catalog })
  assert.equal(settings.internoId, null)
  assert.equal(settings.complete, true) // el INTERNO NO es requerido para que "complete" sea true
})

test('createReviewModel for ticket builds editable fields from proposal', () => {
  const analysis = {
    upload_token: 'tok',
    proposal: {
      fecha: '2026-07-30', hora: '13:30:56', litros: '430', km_hora: '3362', remito: '9938226',
      ruc: '80015646-0', razon_social_emisor: 'PETROBRAS', producto: 'DIESEL EURO 5 S-50',
      nro_tarjeta: '7002650831010234', proveedor_id: 2, tipo_combustible_id: 1, warnings: [],
    },
  }
  const review = createReviewModel(analysis, baseSettings(), '2026-07-31', FUEL_TIPO_TICKET)
  assert.equal(review.tipo, FUEL_TIPO_TICKET)
  assert.equal(review.fecha_carga, '2026-07-30')
  assert.equal(review.litros, '430')
  assert.equal(review.km_hora, '3362')
  assert.equal(review.remito, '9938226')
  assert.equal(review.proveedor_id, 2)
  assert.equal(review.razon_social_emisor, 'PETROBRAS')
})

test('createReviewModel for remito_interno uses INTERNO from settings', () => {
  const analysis = {
    upload_token: 'tok',
    proposal: {
      fecha: '2026-07-30', hora: '13:42', litros: '162', kilometros: '7153.1', remito: '0007222',
      lugar_carga: 'Gsibg', patente_observada: 'AAXO300', firmante: 'Fernando',
      contacto: 'n@y', tipo: 'INTERNO/GASOIL', tipo_combustible_id: 1, warnings: [],
    },
  }
  const review = createReviewModel(analysis, baseSettings(), '2026-07-31', FUEL_TIPO_REMITO_INTERNO)
  assert.equal(review.tipo, FUEL_TIPO_REMITO_INTERNO)
  assert.equal(review.km_hora, '7153.1')  // OCR lo pre-carga en km_hora (editable)
  assert.equal(review.proveedor_id, 29)  // INTERNO
  assert.equal(review.proveedor_nombre, 'INTERNO FORESTAL PARAGUAY')
})

test('createReviewModel for remito_interno warns when INTERNO missing', () => {
  const analysis = {
    upload_token: 'tok',
    proposal: { fecha: '2026-07-30', litros: '162', kilometros: '7153.1', remito: '0007222', warnings: [] },
  }
  const settings = { ...baseSettings(), internoId: null, internoNombre: '' }
  const review = createReviewModel(analysis, settings, '2026-07-31', FUEL_TIPO_REMITO_INTERNO)
  assert.ok(review.configurationWarnings.some((w) => /INTERNO/.test(w)))
})

test('buildConfirmPayload for ticket validates remito length and provider', () => {
  const review = {
    upload_token: 'tok', tipo: FUEL_TIPO_TICKET,
    fecha_carga: '2026-07-30', litros: '430', km_hora: '3362', remito: '9938226',
    proveedor_id: 2, paniol_id: null, tipo_combustible_id: 1, observaciones: 'OK',
  }
  const payload = buildConfirmPayload(review, baseSettings(), FUEL_TIPO_TICKET)
  assert.equal(payload.remito, '9938226')
  assert.equal(payload.fecha_carga, '2026-07-30')
  assert.equal(payload.litros, 430)
  assert.equal(payload.km_hora, 3362)
  assert.equal(payload.proveedor_id, 2)
  assert.equal(payload.equipo_id, 4)
})

test('buildConfirmPayload for ticket rejects bad remito length', () => {
  const review = {
    upload_token: 'tok', tipo: FUEL_TIPO_TICKET,
    fecha_carga: '2026-07-30', litros: '430', km_hora: '3362', remito: '12345',
    proveedor_id: 2, paniol_id: null, tipo_combustible_id: 1,
  }
  assert.throws(() => buildConfirmPayload(review, baseSettings(), FUEL_TIPO_TICKET), /7 dígitos/)
})

test('buildConfirmPayload for ticket rejects missing provider', () => {
  const review = {
    upload_token: 'tok', tipo: FUEL_TIPO_TICKET,
    fecha_carga: '2026-07-30', litros: '430', km_hora: '3362', remito: '9938226',
    proveedor_id: null, paniol_id: null, tipo_combustible_id: 1,
  }
  assert.throws(() => buildConfirmPayload(review, baseSettings(), FUEL_TIPO_TICKET), /proveedor/i)
})

test('buildConfirmPayload for remito_interno accepts 6-7 digit remito and does not send proveedor_id (backend forces INTERNO)', () => {
  const review = {
    upload_token: 'tok', tipo: FUEL_TIPO_REMITO_INTERNO,
    fecha_carga: '2026-07-30', litros: '162', km_hora: '7153.1', remito: '0007222',
    paniol_id: null, tipo_combustible_id: 1, observaciones: '',
  }
  const payload = buildConfirmPayload(review, baseSettings(), FUEL_TIPO_REMITO_INTERNO)
  assert.equal(payload.remito, '0007222')
  // El payload NO lleva proveedor_id; el backend lo fuerza al INTERNO
  // (ver backend/fuel_image_service.py: confirm_remito_interno).
  assert.equal(payload.proveedor_id, undefined)
  // 6-digit remito
  const review2 = { ...review, remito: '123456' }
  const payload2 = buildConfirmPayload(review2, baseSettings(), FUEL_TIPO_REMITO_INTERNO)
  assert.equal(payload2.remito, '123456')
})

test('buildConfirmPayload for remito_interno rejects remito with wrong length', () => {
  const review = {
    upload_token: 'tok', tipo: FUEL_TIPO_REMITO_INTERNO,
    fecha_carga: '2026-07-30', litros: '162', km_hora: '7153.1', remito: '12345',
    paniol_id: null, tipo_combustible_id: 1,
  }
  assert.throws(() => buildConfirmPayload(review, baseSettings(), FUEL_TIPO_REMITO_INTERNO), /6 o 7 dígitos/)
})

test('buildConfirmPayload for remito_interno fails if INTERNO missing in settings', () => {
  const review = {
    upload_token: 'tok', tipo: FUEL_TIPO_REMITO_INTERNO,
    fecha_carga: '2026-07-30', litros: '162', km_hora: '7153.1', remito: '0007222',
    paniol_id: null, tipo_combustible_id: 1,
  }
  const settings = { ...baseSettings(), internoId: null, internoNombre: '' }
  assert.throws(() => buildConfirmPayload(review, settings, FUEL_TIPO_REMITO_INTERNO), /INTERNO/i)
})

test('buildConfirmPayload rejects incomplete settings', () => {
  const review = {
    upload_token: 'tok', tipo: FUEL_TIPO_TICKET,
    fecha_carga: '2026-07-30', litros: '430', km_hora: '3362', remito: '9938226',
    proveedor_id: 2,
  }
  const settings = baseSettings()
  settings.equipoId = null  // incompleto
  assert.throws(() => buildConfirmPayload(review, settings, FUEL_TIPO_TICKET), /incompleta/i)
})

test('transitionReviewState allows the expected fuel flow', () => {
  assert.equal(transitionReviewState('selecting', 'PROCESS'), 'processing')
  assert.equal(transitionReviewState('processing', 'ANALYZED'), 'reviewing')
  assert.equal(transitionReviewState('reviewing', 'CONFIRM'), 'confirming')
  assert.equal(transitionReviewState('confirming', 'CONFIRMED'), 'success')
  assert.throws(() => transitionReviewState('selecting', 'CONFIRM'), /no permitida/)
  assert.throws(() => transitionReviewState('desconocido', 'PROCESS'), /desconocido/i)
})
