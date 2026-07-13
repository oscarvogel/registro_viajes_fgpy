import assert from 'node:assert/strict'
import test from 'node:test'
import {
  analyzeTripImage,
  confirmTripImage,
  createTripImageObjectUrl,
  fetchTripImageBlob,
  mapTripImageError,
  prepareTripImageForUpload,
  revokeTripImageObjectUrl,
  tripImageUrl,
} from '../src/services/tripImage.js'
import {
  buildConfirmPayload,
  createReviewModel,
  formatWeight,
  parseWeight,
  readTripImageSettings,
  transitionReviewState,
} from '../src/services/tripImageReview.js'

const file = () => new Blob(['image'], { type: 'image/jpeg' })

test('analyzeTripImage posts only browser FormData and returns response data', async () => {
  let request
  const http = { post: async (...args) => { request = args; return { data: { upload_token: 'memory-only', proposal: {} } } } }
  const image = file()
  const result = await analyzeTripImage(image, http, 'https://api.test')
  assert.equal(request[0], 'https://api.test/registro-viaje/imagen/analizar')
  assert.equal(request[1].get('file').size, image.size)
  assert.equal(request[1].get('file').type, image.type)
  assert.deepEqual([...request[1].keys()], ['file'])
  assert.equal(request.length, 2)
  assert.deepEqual(result, { upload_token: 'memory-only', proposal: {} })
})

test('analyzeTripImage rejects missing and non file-like input before HTTP', async () => {
  let calls = 0
  const http = { post: async () => { calls += 1 } }
  await assert.rejects(() => analyzeTripImage(null, http), /imagen/i)
  await assert.rejects(() => analyzeTripImage({ name: 'x.jpg' }, http), /imagen/i)
  await assert.rejects(() => analyzeTripImage({ name: 'fake.jpg', type: 'image/jpeg', arrayBuffer: async () => new ArrayBuffer(0) }, http), /imagen/i)
  assert.equal(calls, 0)
})

test('confirmTripImage posts payload unchanged and tripImageUrl validates and encodes id', async () => {
  const payload = { upload_token: 'opaque' }
  let request
  const http = { post: async (...args) => { request = args; return { data: { id: 9 } } } }
  assert.deepEqual(await confirmTripImage(payload, http, '/api'), { id: 9 })
  assert.deepEqual(request, ['/api/registro-viaje/imagen/confirmar', payload])
  assert.equal(tripImageUrl(12, '/api'), '/api/registro-viaje/imagenes/12')
  for (const id of [0, -1, 1.2, '1', '../secret']) assert.throws(() => tripImageUrl(id, '/api'), /id/i)
})

test('fetchTripImageBlob uses authenticated injected GET and validates image Blob', async () => {
  const blob = new Blob(['image'], { type: 'image/jpeg' })
  let request
  const http = { get: async (...args) => { request = args; return { data: blob } } }
  assert.equal(await fetchTripImageBlob(12, http, '/api'), blob)
  assert.deepEqual(request, ['/api/registro-viaje/imagenes/12', { responseType: 'blob' }])
  await assert.rejects(() => fetchTripImageBlob(12, { get: async () => ({ data: new Blob(['x'], { type: 'text/html' }) }) }, '/api'), /imagen/i)
})

test('image object URL helpers inject lifecycle API and reject non-image data', () => {
  const blob = new Blob(['image'], { type: 'image/png' })
  const calls = []
  const urlApi = { createObjectURL: (value) => { calls.push(['create', value]); return 'blob:safe' }, revokeObjectURL: (url) => calls.push(['revoke', url]) }
  assert.equal(createTripImageObjectUrl(blob, urlApi), 'blob:safe')
  revokeTripImageObjectUrl('blob:safe', urlApi)
  assert.deepEqual(calls, [['create', blob], ['revoke', 'blob:safe']])
  assert.throws(() => createTripImageObjectUrl(new Blob(['x'], { type: '' }), urlApi), /imagen/i)
})

test('mapTripImageError returns safe Spanish actions without reflecting backend details', () => {
  const expected = {
    400: ['La solicitud de imagen no es válida.', false], 401: ['Tu sesión venció. Iniciá sesión nuevamente.', false],
    403: ['No tenés permiso para cargar esta imagen.', false], 409: ['Este comprobante ya fue confirmado.', false],
    410: ['La imagen venció. Volvé a analizarla.', true], 413: ['La imagen es demasiado grande.', false],
    422: ['Revisá los datos detectados antes de confirmar.', false], 502: ['El servicio de lectura no está disponible.', true],
    503: ['El servicio de lectura no está disponible.', true], 504: ['El servicio tardó demasiado en responder.', true],
    404: ['No se encontró la imagen solicitada.', false], 429: ['Hay demasiadas solicitudes. Esperá un momento e intentá nuevamente.', true],
    500: ['El servidor no pudo procesar la imagen.', true],
  }
  for (const [status, [message, retry]] of Object.entries(expected)) {
    const mapped = mapTripImageError({ response: { status: Number(status), data: { detail: 'C:\\secret upload_token=abc' } } })
    assert.deepEqual(mapped, { message, action: retry ? 'retry' : 'review', retry })
    assert.doesNotMatch(JSON.stringify(mapped), /secret|token|abc/i)
  }
  assert.deepEqual(mapTripImageError({ message: 'Network Error /private/token' }), {
    message: 'No hay conexión. Verificá Internet e intentá nuevamente.', action: 'retry', retry: true,
  })
})

const storage = (values) => ({ getItem: (key) => values[key] ?? null })
const catalog = {
  empleados: [{ id: 7, nombre: ' Ana ', apellido: ' Pérez ', activo: true, meta: { secret: 'user' } }],
  equipos: [{ id: 2, patente: 'AB 123 CD', descripcion: ' Camión ', activo: true, meta: { secret: 'truck' } }],
  unidadesNegocio: [{ id: 4, descripcion: ' Forestal ', prefijo: ' F ', activo: true, meta: { secret: 'unit' } }],
  proveedores: [{ id: 8, nombre: 'Proveedor', activo: true }, { id: 9, nombre: 'Inactivo', activo: false }],
}

test('readTripImageSettings parses storage, normalizes config and matches active catalogs', () => {
  const result = readTripImageSettings({ storage: storage({ user: '{"id":7}', default_patente: ' ab 123 cd ', default_unidad_negocio: '4' }), catalog })
  assert.deepEqual(result, {
    userId: 7, user: { id: 7, nombre: 'Ana', apellido: 'Pérez', activo: true },
    patente: 'AB 123 CD', equipoId: 2,
    equipo: { id: 2, patente: 'AB 123 CD', descripcion: 'Camión', activo: true },
    unidadNegocioId: 4,
    unidadNegocio: { id: 4, descripcion: 'Forestal', prefijo: 'F', activo: true }, activeProviderIds: [8],
    missing: [], errors: [], complete: true,
  })
  assert.ok(Object.isFrozen(result))
  assert.ok(Object.isFrozen(result.user) && Object.isFrozen(result.equipo) && Object.isFrozen(result.unidadNegocio))
  assert.ok(Object.isFrozen(result.activeProviderIds) && Object.isFrozen(result.missing) && Object.isFrozen(result.errors))
  assert.equal('meta' in result.user, false)
  assert.equal('meta' in result.equipo, false)
  assert.equal('meta' in result.unidadNegocio, false)
  assert.equal(catalog.empleados[0].nombre, ' Ana ')
  assert.equal(catalog.empleados[0].meta.secret, 'user')
})

test('readTripImageSettings safely reports corrupt, missing or inactive settings', () => {
  const result = readTripImageSettings({ storage: storage({ user: 'oops', default_patente: 'XX', default_unidad_negocio: '-1' }), catalog })
  assert.equal(result.complete, false)
  assert.deepEqual([...result.missing].sort(), ['patente', 'unidad_negocio', 'user'])
  assert.ok(result.errors.length >= 2)
})

test('readTripImageSettings requires explicit active flags and tolerates throwing storage', () => {
  const missingFlags = {
    empleados: [{ id: 7, nombre: 'Ana' }], equipos: [{ id: 2, patente: 'AB 123 CD' }],
    unidadesNegocio: [{ id: 4 }], proveedores: [{ id: 8 }],
  }
  const inactive = readTripImageSettings({ storage: storage({ user: '{"id":7}', default_patente: 'AB 123 CD', default_unidad_negocio: '4' }), catalog: missingFlags })
  assert.equal(inactive.complete, false)
  assert.deepEqual(inactive.activeProviderIds, [])
  const throwing = readTripImageSettings({ storage: { getItem: () => { throw new Error('C:\\secret token') } }, catalog })
  assert.equal(throwing.complete, false)
  assert.doesNotMatch(JSON.stringify(throwing), /secret|token/i)
})

const analysis = { upload_token: 'opaque', proposal: {
  fecha_remision: '2026-07-12', numero_remision_fpv: '001-002-0000003', proveedor_id: 8,
  peso_bruto_destino: 49.69, tara_destino: '17.080', neto_destino: 32.61,
  patente_observada: 'ZZ999ZZ', chofer_observado: 'Otra Persona', confidence: 0.91, warnings: ['borroso'],
} }
const settings = readTripImageSettings({ storage: storage({ user: '{"id":7}', default_patente: ' ab 123 cd ', default_unidad_negocio: '4' }), catalog })

test('createReviewModel exposes only concrete configuration mismatches', () => {
  const review = createReviewModel(analysis, settings, '2026-07-13')
  assert.equal(review.upload_token, 'opaque')
  assert.equal(review.fecha_recepcion, '2026-07-13')
  assert.equal(review.numero_remision_fpv, '001-002-0000003')
  assert.deepEqual([review.peso_bruto_destino, review.tara_destino, review.neto_destino], ['49.690', '17.080', '32.610'])
  assert.equal(review.observaciones, '')
  assert.equal(review.config.patente, 'AB 123 CD')
  assert.ok(Object.isFrozen(review.config))
  assert.ok(Object.isFrozen(review.config.user) && Object.isFrozen(review.config.unidadNegocio))
  assert.equal('meta' in review.config.user, false)
  assert.equal('meta' in review.config.equipo, false)
  assert.equal('meta' in review.config.unidadNegocio, false)
  assert.throws(() => { review.config.user.nombre = 'Mutado' }, TypeError)
  assert.equal(catalog.empleados[0].nombre, ' Ana ')
  assert.equal(review.observed.patente, 'ZZ999ZZ')
  assert.deepEqual(review.warnings, ['borroso'])
  assert.deepEqual(review.configurationWarnings, [
    'La foto parece indicar ZZ999ZZ; en Ajustes figura AB 123 CD.',
    'La foto parece indicar Otra Persona; el usuario actual es Pérez Ana.',
  ])
})

test('prepareTripImageForUpload compresses oversized mobile images before upload', async () => {
  const large = new File([new Uint8Array(2 * 1024)], 'remito.png', { type: 'image/png' })
  const compressed = new Blob(['compressed'], { type: 'image/jpeg' })
  const calls = []
  const imageApi = {
    createImageBitmap: async (blob) => {
      calls.push(['decode', blob])
      return { width: 4000, height: 3000, close: () => calls.push(['close']) }
    },
    createCanvas: () => {
      const canvas = {
        width: 0,
        height: 0,
        getContext: () => ({ drawImage: (...args) => calls.push(['drawImage', canvas.width, canvas.height, args.length]) }),
        toBlob: (callback, type, quality) => {
          calls.push(['toBlob', canvas.width, canvas.height, type, quality])
          callback(compressed)
        },
      }
      return canvas
    },
  }

  const result = await prepareTripImageForUpload(large, { maxBytes: 1024, maxSide: 2000, imageApi })

  assert.equal(result.size, compressed.size)
  assert.equal(result.type, 'image/jpeg')
  assert.equal(result.name, 'remito.jpg')
  assert.deepEqual(calls, [
    ['decode', large],
    ['drawImage', 2000, 1500, 5],
    ['toBlob', 2000, 1500, 'image/jpeg', 0.82],
    ['close'],
  ])
})

test('createReviewModel accepts observed full driver in either name order', () => {
  for (const chofer_observado of ['Ana Pérez', 'Pérez Ana']) {
    const review = createReviewModel({ ...analysis, proposal: { ...analysis.proposal, chofer_observado } }, settings, '2026-07-13')
    assert.equal(review.configurationWarnings?.some((warning) => /usuario actual/i.test(warning)), false)
  }
})

test('createReviewModel omits configuration warnings when OCR matches or is absent', () => {
  for (const observed of ['Ana Pérez', 'Pérez Ana', null]) {
    const review = createReviewModel({
      ...analysis,
      proposal: {
        ...analysis.proposal,
        patente_observada: observed ? 'AB123CD' : null,
        chofer_observado: observed,
      },
    }, settings, '2026-07-13')
    assert.deepEqual(review.configurationWarnings, [])
  }
})

test('weight helpers preserve three decimals and conservatively reject invalid input', () => {
  assert.equal(formatWeight('49.690'), '49.690')
  assert.equal(formatWeight('17,08'), '17.080')
  assert.equal(parseWeight('32,610'), 32.61)
  for (const value of ['1e3', 'NaN', 'Infinity', '-1', '1,234.5', '1.2.3', '']) assert.throws(() => parseWeight(value), /peso/i)
})

test('buildConfirmPayload emits exact backend fields and takes config only from settings', () => {
  const review = createReviewModel(analysis, settings, '2026-07-13')
  review.observaciones = '  controlado  '
  review.patente = 'OCR-CANNOT-WIN'
  const payload = buildConfirmPayload(review, settings)
  assert.deepEqual(Object.keys(payload), [
    'upload_token', 'fecha_remision', 'fecha_recepcion', 'numero_remision_fpv', 'proveedor_id', 'patente',
    'unidad_negocio_id', 'peso_bruto_destino', 'tara_destino', 'neto_destino', 'observaciones',
  ])
  assert.deepEqual(payload, {
    upload_token: 'opaque', fecha_remision: '2026-07-12', fecha_recepcion: '2026-07-13',
    numero_remision_fpv: '001-002-0000003', proveedor_id: 8, patente: 'AB 123 CD', unidad_negocio_id: 4,
    peso_bruto_destino: 49.69, tara_destino: 17.08, neto_destino: 32.61, observaciones: 'controlado',
  })
})

test('buildConfirmPayload validates dates, remito, provider, config, positive weights and balance', () => {
  const valid = createReviewModel(analysis, settings, '2026-07-13')
  for (const mutate of [
    (r) => { r.fecha_remision = '13/07/2026' }, (r) => { r.numero_remision_fpv = '1-2-3' },
    (r) => { r.fecha_remision = '2026-02-30' },
    (r) => { r.proveedor_id = null }, (r) => { r.peso_bruto_destino = '0' },
    (r) => { r.neto_destino = '32.590' },
  ]) {
    const invalid = structuredClone(valid)
    mutate(invalid)
    assert.throws(() => buildConfirmPayload(invalid, settings))
  }
  assert.doesNotThrow(() => buildConfirmPayload(valid, { ...settings, complete: false }))
  for (const fake of [
    { ...settings, user: null, complete: true },
    { ...settings, equipo: null, complete: true },
    { ...settings, unidadNegocio: null, complete: true },
    { ...settings, patente: 'FAKE', complete: true },
    { ...settings, unidadNegocioId: 999, complete: true },
    { ...settings, activeProviderIds: [], complete: true },
    { ...settings, user: { ...settings.user, activo: false }, complete: true },
  ]) assert.throws(() => buildConfirmPayload(valid, fake), /configuración|proveedor/i)
})

test('buildConfirmPayload trims token and rejects blank or unauthorized provider', () => {
  const valid = createReviewModel({ ...analysis, upload_token: '  opaque  ' }, settings, '2026-07-13')
  assert.equal(buildConfirmPayload(valid, settings).upload_token, 'opaque')
  valid.upload_token = '   '
  assert.throws(() => buildConfirmPayload(valid, settings), /imagen/i)
  valid.upload_token = 'opaque'
  valid.proveedor_id = 9
  assert.throws(() => buildConfirmPayload(valid, settings), /proveedor/i)
})

test('buildConfirmPayload checks balance with exact integer millitons', () => {
  const boundary = createReviewModel({ ...analysis, proposal: {
    ...analysis.proposal, peso_bruto_destino: '100.000', tara_destino: '17.080', neto_destino: '82.910',
  } }, settings, '2026-07-13')
  assert.deepEqual([
    buildConfirmPayload(boundary, settings).peso_bruto_destino,
    buildConfirmPayload(boundary, settings).tara_destino,
    buildConfirmPayload(boundary, settings).neto_destino,
  ], [100, 17.08, 82.91])
  boundary.neto_destino = '82.909'
  assert.throws(() => buildConfirmPayload(boundary, settings), /pesos/i)
})

test('transitionReviewState allows only defined workflow transitions', () => {
  assert.equal(transitionReviewState('selecting', 'PROCESS'), 'processing')
  assert.equal(transitionReviewState('processing', 'ANALYZED'), 'reviewing')
  assert.equal(transitionReviewState('reviewing', 'CONFIRM'), 'confirming')
  assert.equal(transitionReviewState('confirming', 'CONFIRMED'), 'success')
  assert.equal(transitionReviewState('error', 'RETRY'), 'processing')
  assert.equal(transitionReviewState('error', 'REVIEW'), 'reviewing')
  assert.equal(transitionReviewState('processing', 'FAIL'), 'error')
  assert.equal(transitionReviewState('confirming', 'FAIL'), 'error')
  assert.throws(() => transitionReviewState('selecting', 'CONFIRMED'), /transición/i)
  assert.throws(() => transitionReviewState('unknown', 'PROCESS'), /estado/i)
})
