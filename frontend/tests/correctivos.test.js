import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildCorrectivoPayload,
  resolveDefaultCorrectivoEquipo,
  validateCorrectivoForm,
} from '../src/services/correctivos.js'

test('resolveDefaultCorrectivoEquipo normaliza patente como combustible', () => {
  const equipos = [
    { id: 10, patente: 'AA PL 657', descripcion: 'Camion' },
    { id: 11, patente: 'BBBB111', descripcion: 'Otro' },
  ]

  const equipo = resolveDefaultCorrectivoEquipo(equipos, 'aapl657')
  assert.equal(equipo.id, 10)
})

test('buildCorrectivoPayload no incluye identidad y limpia opcionales', () => {
  const payload = buildCorrectivoPayload({
    form: {
      fecha: '2026-08-11',
      equipo_id: '10',
      km_hora: '185420',
      descripcion: '  Pinchadura  ',
      externo: false,
      proveedor_id: '20',
      mecanico_id: '8',
      unidad_negocio_id: '1',
      moneda_id: '1',
      cambio: '1',
      orden_servicio: ' REF-1 ',
      usuario: 'forjado',
      cerrado_por: 'forjado',
    },
    trabajos: [{
      tipo_tarea_id: '3',
      detalle: ' Reparar cubierta ',
      repuesto_id: '',
      cantidad: '0',
      precio_unitario: '0',
      mecanico_id: '',
      sector_id: '',
      observaciones: ' ok ',
    }],
  })

  assert.equal(payload.equipo_id, 10)
  assert.equal(payload.descripcion, 'Pinchadura')
  assert.equal(payload.proveedor_id, null)
  assert.equal(payload.trabajos[0].repuesto_id, null)
  assert.equal(payload.trabajos[0].detalle, 'Reparar cubierta')
  assert.equal('usuario' in payload, false)
  assert.equal('cerrado_por' in payload, false)
})

test('validateCorrectivoForm exige proveedor solo si es externo', () => {
  const base = {
    fecha: '2026-08-11',
    equipo_id: 10,
    km_hora: 100,
    descripcion: 'Incidencia',
    unidad_negocio_id: 1,
    moneda_id: 1,
    proveedor_id: '',
  }
  const trabajos = [{ tipo_tarea_id: 3, detalle: 'Trabajo' }]

  assert.deepEqual(validateCorrectivoForm({ form: { ...base, externo: false }, trabajos }), [])
  assert.deepEqual(validateCorrectivoForm({ form: { ...base, externo: true }, trabajos }), ['Proveedor'])
})
