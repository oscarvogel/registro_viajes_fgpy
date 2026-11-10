import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import {
  buildViajePayload,
  findEquipoByPatente,
  getUnidadLecturaLabel,
  normalizarLectura,
  toUnidadLecturaLabel,
} from '../src/services/criticalScreens.js'

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')

const EQUIPOS = [
  { id: 1, patente: 'ABC123', unidad_hr_km: 'km' },
  { id: 2, patente: 'XYZ 789', unidad_hr_km: 'hs' },
]

test('el formulario de nuevo viaje muestra el campo de lectura con la unidad', async () => {
  const source = await read('../src/views/NewTrip.vue')
  assert.match(source, /v-model="form\.lectura_camion"/)
  assert.match(source, /Lectura/)
})

test('el formulario consulta la ultima lectura del camion', async () => {
  const source = await read('../src/views/NewTrip.vue')
  assert.match(source, /registro-viaje\/ultima-lectura/)
})

test('el formulario bloquea el envio si falta la lectura cuando el flag esta activo', async () => {
  const source = await read('../src/views/NewTrip.vue')
  assert.match(source, /exigir_lectura_camion/)
  assert.match(source, /lectura_camion/)
})

test('el formulario pide confirmacion cuando la lectura es menor a la anterior', async () => {
  const source = await read('../src/views/NewTrip.vue')
  assert.match(source, /permitir_lectura_menor/)
})

test('el formulario usa el combineRemito compartido y no define uno local', async () => {
  const source = await read('../src/views/NewTrip.vue')
  assert.match(source, /from '\.\.\/services\/criticalScreens\.js'/)
  assert.doesNotMatch(source, /const combineRemito\s*=/)
})

test('el campo de lectura acepta coma decimal porque no es un input number', async () => {
  const source = await read('../src/views/NewTrip.vue')
  const campo = source.match(/<input[^>]*v-model="form\.lectura_camion"[\s\S]*?>/)
  assert.ok(campo, 'no se encontro el input de lectura_camion')
  assert.match(campo[0], /type="text"/)
  assert.match(campo[0], /inputmode="decimal"/)
  assert.doesNotMatch(campo[0], /type="number"/)
})

test('el formulario resuelve la unidad desde el equipo por patente', async () => {
  const source = await read('../src/views/NewTrip.vue')
  assert.match(source, /findEquipoByPatente\(catalog\.equipos,\s*form\.value\.patente\)/)
  assert.match(source, /unidadLecturaLabel/)
})

test('el formulario cachea la ultima lectura en localStorage como fallback', async () => {
  const source = await read('../src/views/NewTrip.vue')
  assert.match(source, /LECTURA_STORAGE_PREFIX/)
  assert.match(source, /localStorage\.getItem\(storageKey\)/)
})

test('el formulario no escribe la unidad cruda: usa la etiqueta amable en todo el bloque', async () => {
  const source = await read('../src/views/NewTrip.vue')
  assert.doesNotMatch(source, /'hs'/)
  assert.doesNotMatch(source, /"hs"/)
})

test('normalizarLectura acepta coma decimal y punto', () => {
  assert.equal(normalizarLectura('1234,5'), 1234.5)
  assert.equal(normalizarLectura('1234.5'), 1234.5)
  assert.equal(normalizarLectura('1.234,5'), 1234.5)
  assert.equal(normalizarLectura(' 1234 '), 1234)
  assert.ok(Number.isNaN(normalizarLectura('')))
  assert.ok(Number.isNaN(normalizarLectura('abc')))
})

test('getUnidadLecturaLabel elige la etiqueta amable segun la unidad del equipo', () => {
  const km = findEquipoByPatente(EQUIPOS, 'abc123')
  const hs = findEquipoByPatente(EQUIPOS, 'xyz789')
  assert.equal(getUnidadLecturaLabel(km), 'km')
  assert.equal(getUnidadLecturaLabel(hs), 'horas')
  assert.equal(getUnidadLecturaLabel(null), 'km')
  assert.equal(getUnidadLecturaLabel({}), 'km')
})

test('toUnidadLecturaLabel convierte la unidad cruda del backend a la etiqueta amable', () => {
  assert.equal(toUnidadLecturaLabel('km'), 'km')
  assert.equal(toUnidadLecturaLabel('hs'), 'horas')
  assert.equal(toUnidadLecturaLabel('HS'), 'horas')
  assert.equal(toUnidadLecturaLabel(null), 'km')
})

test('buildViajePayload incluye la lectura normalizada y el permiso de lectura menor', () => {
  const payload = buildViajePayload({
    form: {
      fecha_remision: '2026-11-09',
      fecha_recepcion: '2026-11-09',
      proveedor_id: 3,
      cliente_id: '',
      remito_prov_tipo: '002',
      remito_prov_sucursal: '001',
      remito_prov_numero: '0008880',
      remito_fpv_tipo: '',
      remito_fpv_sucursal: '',
      remito_fpv_numero: '',
      lote: 'L1',
      peso_bruto_destino: 20,
      tara_destino: 8,
      neto_destino: 12,
      neto_origen: 11,
      chofer_id: 7,
      patente: 'ABC123',
      unidad_negocio_id: 1,
      observaciones: '',
    },
    userId: 7,
    lecturaCamion: '1234,5',
    permitirLecturaMenor: true,
  })

  assert.equal(payload.lectura_camion, 1234.5)
  assert.equal(payload.permitir_lectura_menor, true)
  assert.equal(payload.numero_remision, '002-001-0008880')
  assert.equal(payload.patente, 'ABC123')
})


test('buildViajePayload omite la lectura cuando no es valida y tolera el flag ausente', () => {
  const payload = buildViajePayload({
    form: { chofer_id: 7, patente: 'ABC123' },
    userId: 7,
    lecturaCamion: '',
    permitirLecturaMenor: false,
  })

  assert.equal('lectura_camion' in payload, false)
  assert.equal(payload.permitir_lectura_menor, false)
})
