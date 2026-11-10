export const getStoredUser = (storage = globalThis.localStorage) => {
  const userStr = storage?.getItem('user')
  return userStr ? JSON.parse(userStr) : null
}

export const getStoredUserId = (storage = globalThis.localStorage) => {
  return getStoredUser(storage)?.id || null
}

export const buildHistoryRequests = ({ apiUrl, userId, fechaDesde, fechaHasta }) => {
  const params = {
    chofer_id: userId,
    fecha_desde: fechaDesde,
    fecha_hasta: fechaHasta,
  }

  return [
    { url: `${apiUrl}/historial-viajes`, params },
    { url: `${apiUrl}/movimientos-carreton`, params },
  ]
}

export const normalizeApiList = (data) => {
  return Array.isArray(data) ? data : (data?.items ?? [])
}

export const buildFuelLastKmParams = ({ equipoId, now = new Date() }) => {
  const desde = new Date(now)
  desde.setFullYear(now.getFullYear() - 2)

  return {
    fecha_desde: desde.toISOString().split('T')[0],
    fecha_hasta: now.toISOString().split('T')[0],
    equipo_id: equipoId,
  }
}

export const getLastFuelKmHora = (movimientos) => {
  if (!Array.isArray(movimientos) || movimientos.length === 0) return null
  return parseFloat(movimientos[movimientos.length - 1].km_hora || 0)
}

export const FUEL_REMITO_MAX_LENGTH = 12

export const normalizeFuelRemito = (remito) => String(remito || '').trim().slice(0, FUEL_REMITO_MAX_LENGTH)

export const buildFuelPayload = ({ form, userId }) => ({
  fecha_carga: form.fecha_carga,
  litros: Number(form.litros),
  km_hora: Number(form.km_hora),
  equipo_id: Number(form.equipo_id),
  paniol_id: Number(form.paniol_id),
  remito: normalizeFuelRemito(form.remito),
  observaciones: form.observaciones,
  usuario: userId ? `${userId}` : 'app',
})

export const normalizePatente = (value) => String(value || '').replace(/\s+/g, '').toUpperCase()

export const normalizeKilometraje = (value) => {
  if (typeof value === 'number') return value

  const raw = String(value ?? '').trim()
  if (!raw) return NaN

  const compact = raw.replace(/\s+/g, '')

  if (compact.includes(',') && compact.includes('.')) {
    return Number(compact.replace(/\./g, '').replace(',', '.'))
  }

  if (compact.includes(',')) {
    return Number(compact.replace(',', '.'))
  }

  if (/^\d{1,3}(\.\d{3})+$/.test(compact)) {
    return Number(compact.replace(/\./g, ''))
  }

  return Number(compact)
}

export const findEquipoByPatente = (equipos, patente) => {
  if (!patente || !Array.isArray(equipos)) return null
  const target = normalizePatente(patente)
  return equipos.find((equipo) => normalizePatente(equipo.patente) === target) || null
}

export const findUnidadById = (unidades, unidadId) => {
  if (!unidadId || !Array.isArray(unidades)) return null
  return unidades.find((unidad) => String(unidad.id) === String(unidadId)) || null
}

export const getPendingCarretonLastKm = (pendingRecords, equipoId) => {
  const sameEquipo = (pendingRecords || [])
    .filter((record) => record.record_type === 'carreton' && Number(record.equipo_id) === Number(equipoId))
    .sort((left, right) => (left.local_id || 0) - (right.local_id || 0))

  if (sameEquipo.length === 0) return null
  return normalizeKilometraje(sameEquipo[sameEquipo.length - 1].km_final)
}

export const buildCarretonPayload = ({ form, userId }) => ({
  fecha: form.fecha,
  equipo_id: Number(form.equipo_id),
  unidad_negocio_id: Number(form.unidad_negocio_id),
  hora_inicio_viaje: form.hora_inicio_viaje || null,
  km_inicial: normalizeKilometraje(form.km_inicial),
  km_final: normalizeKilometraje(form.km_final),
  estado_carga: form.estado_carga,
  tipo_maquina_transportada: form.tipo_maquina_transportada.trim(),
  origen_carreton: form.origen_carreton ? form.origen_carreton.trim() : '',
  destino_carreton: form.destino_carreton ? form.destino_carreton.trim() : '',
  usuario: `${userId}`,
})

export const LECTURA_STORAGE_PREFIX = 'lectura_camion_'

// La unidad cruda es la que guarda el backend ('km' | 'hs'); la etiqueta
// amable es la que se muestra al chofer ('km' | 'horas'). El cliente nunca
// manda la unidad: solo la usa para etiquetar el campo.
export const UNIDAD_LECTURA_LABELS = { km: 'km', hs: 'horas' }

export const getUnidadLecturaLabel = (equipo) => {
  const raw = String(equipo?.unidad_hr_km || 'km').toLowerCase()
  return UNIDAD_LECTURA_LABELS[raw] || 'km'
}

export const toUnidadLecturaLabel = (unidad) => {
  const raw = String(unidad || '').toLowerCase()
  return UNIDAD_LECTURA_LABELS[raw] || 'km'
}

export const normalizarLectura = (value) => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : NaN

  const raw = String(value ?? '').trim()
  if (!raw) return NaN

  const compact = raw.replace(/\s+/g, '')

  if (compact.includes(',') && compact.includes('.')) {
    return Number(compact.replace(/\./g, '').replace(',', '.'))
  }

  if (compact.includes(',')) {
    return Number(compact.replace(',', '.'))
  }

  if (/^\d{1,3}(\.\d{3})+$/.test(compact)) {
    return Number(compact.replace(/\./g, ''))
  }

  return Number(compact)
}

export const getPendingViajeLastLectura = (pendingRecords, patente) => {
  const target = normalizePatente(patente)
  if (!target) return null

  const sameCamion = (pendingRecords || [])
    .filter((record) => (record.record_type || 'viaje') === 'viaje'
      && normalizePatente(record.patente) === target
      && record.lectura_camion !== undefined
      && record.lectura_camion !== null
      && record.lectura_camion !== '')
    .sort((left, right) => (left.local_id || 0) - (right.local_id || 0))

  if (sameCamion.length === 0) return null

  const value = normalizarLectura(sameCamion[sameCamion.length - 1].lectura_camion)
  return Number.isFinite(value) ? value : null
}

const padZeros = (value, length) => String(value || '').padStart(length, '0')

export const combineRemito = (tipo, sucursal, numero) => {
  if (!tipo && !sucursal && !numero) return ''
  const t = padZeros(tipo, 3)
  const s = padZeros(sucursal, 3)
  const n = padZeros(numero, 7)
  return `${t}-${s}-${n}`
}

export const buildViajePayload = ({ form, userId, lecturaCamion, permitirLecturaMenor }) => {
  const payload = {
    fecha_remision: form.fecha_remision,
    fecha_recepcion: form.fecha_recepcion,
    proveedor_id: form.proveedor_id,
    cliente_id: form.cliente_id,
    numero_remision: combineRemito(form.remito_prov_tipo, form.remito_prov_sucursal, form.remito_prov_numero),
    numero_remision_fpv: combineRemito(form.remito_fpv_tipo, form.remito_fpv_sucursal, form.remito_fpv_numero),
    lote: form.lote,
    peso_bruto_destino: Number(form.peso_bruto_destino),
    tara_destino: Number(form.tara_destino),
    neto_destino: Number(form.neto_destino),
    neto_origen: Number(form.neto_origen),
    chofer_id: Number(form.chofer_id || userId),
    patente: form.patente,
    unidad_negocio_id: Number(form.unidad_negocio_id || 1),
    observaciones: form.observaciones,
    permitir_lectura_menor: Boolean(permitirLecturaMenor),
  }

  const lectura = normalizarLectura(lecturaCamion)
  if (Number.isFinite(lectura) && lectura > 0) {
    payload.lectura_camion = lectura
  }

  return payload
}
