import { FUEL_TIPO_REMITO_INTERNO, FUEL_TIPO_TICKET } from './fuelImage.js'

const positiveInteger = (value) => {
  const number = typeof value === 'string' && /^\d+$/.test(value.trim()) ? Number(value) : value
  return Number.isInteger(number) && number > 0 ? number : null
}

const scalarText = (value) => String(value ?? '').trim()
const active = (item) => item?.activo === true
const list = (value) => Array.isArray(value) ? value : []
const normalizedText = (value) => String(value ?? '').trim().toUpperCase().replace(/[^A-Z0-9]/g, '')

const userSnapshot = (value) => value ? Object.freeze({
  id: positiveInteger(value.id),
  nombre: scalarText(value.nombre),
  apellido: scalarText(value.apellido),
  activo: true,
}) : null

const equipmentSnapshot = (value) => value ? Object.freeze({
  id: positiveInteger(value.id),
  patente: scalarText(value.patente).toUpperCase(),
  descripcion: scalarText(value.descripcion),
  activo: true,
}) : null

const unitSnapshot = (value) => value ? Object.freeze({
  id: positiveInteger(value.id),
  descripcion: scalarText(value.descripcion),
  prefijo: scalarText(value.prefijo),
  activo: true,
}) : null

const findInternoProvider = (catalog) => {
  const proveedores = list(catalog?.proveedores).filter(active)
  return proveedores.find((item) =>
    String(item?.razon_social ?? '').toUpperCase().includes('INTERNO')
  ) || null
}

export const readFuelImageSettings = ({ storage, catalog = {} }) => {
  const errors = []
  const stored = {}
  for (const key of ['user', 'default_patente', 'default_unidad_negocio']) {
    try {
      stored[key] = storage?.getItem(key) ?? null
    } catch {
      stored[key] = null
      errors.push('No se pudo leer la configuración guardada.')
    }
  }
  let userId = null
  try {
    userId = positiveInteger(JSON.parse(stored.user ?? 'null')?.id)
  } catch {
    errors.push('La sesión guardada no es válida.')
  }
  const patente = String(stored.default_patente ?? '').trim().toUpperCase()
  const unidadNegocioId = positiveInteger(stored.default_unidad_negocio)
  if (!unidadNegocioId && stored.default_unidad_negocio) errors.push('La unidad de negocio guardada no es válida.')

  const user = userSnapshot(list(catalog.empleados).find((item) => active(item) && positiveInteger(item.id) === userId))
  const equipo = equipmentSnapshot(list(catalog.equipos).find((item) => active(item) && normalizedText(item.patente) === normalizedText(patente)))
  const unidadNegocio = unitSnapshot(list(catalog.unidadesNegocio).find((item) => active(item) && positiveInteger(item.id) === unidadNegocioId))
  const interno = findInternoProvider(catalog)
  const activeProviderIds = Object.freeze(list(catalog.proveedores)
    .filter(active)
    .map((item) => positiveInteger(item.id))
    .filter(Boolean))
  const missing = []
  if (!user) missing.push('user')
  if (!patente || !equipo) missing.push('patente')
  if (!unidadNegocio) missing.push('unidad_negocio')
  // Para remito interno, el INTERNO es mandatorio; sin el, no se puede
  // confirmar. Lo chequeamos en createReviewModel con un mensaje claro.
  return Object.freeze({
    userId: user ? positiveInteger(user.id) : null,
    user,
    patente,
    equipoId: equipo ? positiveInteger(equipo.id) : null,
    equipo,
    unidadNegocioId: unidadNegocio ? positiveInteger(unidadNegocio.id) : null,
    unidadNegocio,
    internoId: interno ? positiveInteger(interno.id) : null,
    internoNombre: interno ? scalarText(interno.razon_social) : '',
    activeProviderIds,
    missing: Object.freeze(missing),
    errors: Object.freeze(errors),
    complete: missing.length === 0,
  })
}

const toIsoDate = (value) => {
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value
  return ''
}

const TICKET_REMITO = /^\d{7}$/
const REMITO_INTERNO = /^\d{6,7}$/

const createTicketReview = (analysis, settings) => {
  const proposal = analysis?.proposal || {}
  const warnings = [...list(proposal.warnings)]
  const fecha = toIsoDate(proposal.fecha)
  const remito = scalarText(proposal.remito)
  const litros = scalarText(proposal.litros)
  const kmHora = scalarText(proposal.km_hora)
  return {
    upload_token: analysis?.upload_token,
    tipo: FUEL_TIPO_TICKET,
    fecha_carga: fecha,
    hora_carga: scalarText(proposal.hora),
    litros,
    km_hora: kmHora,
    remito,
    razon_social_emisor: scalarText(proposal.razon_social_emisor),
    producto: scalarText(proposal.producto),
    nro_tarjeta: scalarText(proposal.nro_tarjeta),
    ruc: scalarText(proposal.ruc),
    proveedor_id: positiveInteger(proposal.proveedor_id),
    proveedor_candidato: scalarText(proposal.proveedor_candidato),
    tipo_combustible_id: positiveInteger(proposal.tipo_combustible_id),
    paniol_id: null,
    observaciones: '',
    config: {
      user: userSnapshot(settings?.user),
      patente: settings?.patente || '',
      equipo: equipmentSnapshot(settings?.equipo),
      unidadNegocio: unitSnapshot(settings?.unidadNegocio),
    },
    warnings,
    configurationWarnings: [],
  }
}

const createRemitoReview = (analysis, settings) => {
  const proposal = analysis?.proposal || {}
  const warnings = [...list(proposal.warnings)]
  const configurationWarnings = []
  if (!settings?.internoId) {
    configurationWarnings.push(
      'Falta el proveedor INTERNO en el catálogo. Contactá a soporte antes de cargar remitos internos.'
    )
  }
  return {
    upload_token: analysis?.upload_token,
    tipo: FUEL_TIPO_REMITO_INTERNO,
    fecha_carga: toIsoDate(proposal.fecha),
    hora_carga: scalarText(proposal.hora),
    litros: scalarText(proposal.litros),
    km_hora: scalarText(proposal.kilometros),
    remito: scalarText(proposal.remito),
    lugar_carga: scalarText(proposal.lugar_carga),
    patente_observada: scalarText(proposal.patente_observada),
    firmante: scalarText(proposal.firmante),
    contacto: scalarText(proposal.contacto),
    tipo_producto: scalarText(proposal.tipo),
    proveedor_id: settings?.internoId ?? null,
    proveedor_nombre: settings?.internoNombre || '',
    tipo_combustible_id: positiveInteger(proposal.tipo_combustible_id),
    paniol_id: null,
    observaciones: '',
    config: {
      user: userSnapshot(settings?.user),
      patente: settings?.patente || '',
      equipo: equipmentSnapshot(settings?.equipo),
      unidadNegocio: unitSnapshot(settings?.unidadNegocio),
    },
    warnings,
    configurationWarnings,
  }
}

export const createReviewModel = (analysis, settings, _today, tipo) => {
  if (tipo === FUEL_TIPO_REMITO_INTERNO) return createRemitoReview(analysis, settings)
  return createTicketReview(analysis, settings)
}

const ISO_DATE = /^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$/

const requireDate = (value) => {
  const text = String(value)
  const match = ISO_DATE.exec(text)
  const date = match ? new Date(`${text}T00:00:00Z`) : null
  const valid = date
    && date.getUTCFullYear() === Number(text.slice(0, 4))
    && date.getUTCMonth() + 1 === Number(text.slice(5, 7))
    && date.getUTCDate() === Number(text.slice(8, 10))
  if (!valid) throw new TypeError('La fecha debe usar formato ISO válido.')
  return value
}

const requireNumber = (value, field, allowZero = false) => {
  const number = Number(String(value ?? '').replace(',', '.'))
  if (!Number.isFinite(number)) throw new TypeError(`${field} debe ser un número válido.`)
  if (allowZero ? number < 0 : number <= 0) throw new TypeError(`${field} debe ser mayor a 0.`)
  return number
}

const requireInt = (value, field, allowZero = false) => {
  const number = Number(String(value ?? '').trim())
  if (!Number.isFinite(number) || !Number.isInteger(number)) {
    throw new TypeError(`${field} debe ser un entero válido.`)
  }
  if (allowZero ? number < 0 : number <= 0) throw new TypeError(`${field} debe ser mayor a 0.`)
  return number
}

const requireRemito = (value, expected) => {
  const text = scalarText(value)
  if (expected === 7 && !TICKET_REMITO.test(text)) {
    throw new TypeError('El remito debe tener 7 dígitos.')
  }
  if (expected === '6-7' && !REMITO_INTERNO.test(text)) {
    throw new TypeError('El remito debe tener 6 o 7 dígitos.')
  }
  return text
}

const validConfig = (settings) => {
  const userId = positiveInteger(settings?.userId)
  const equipoId = positiveInteger(settings?.equipoId)
  const unidadId = positiveInteger(settings?.unidadNegocioId)
  return Boolean(
    userId
    && equipoId
    && unidadId
    && settings?.user?.activo === true
    && positiveInteger(settings.user.id) === userId
    && settings?.equipo?.activo === true
    && positiveInteger(settings.equipo.id) === equipoId
    && normalizedText(settings.equipo.patente) === normalizedText(settings.patente)
    && settings?.unidadNegocio?.activo === true
    && positiveInteger(settings.unidadNegocio.id) === unidadId
  )
}

const requireConfig = (settings) => {
  if (!validConfig(settings)) {
    throw new TypeError('La configuración del viaje está incompleta.')
  }
}

const buildTicketPayload = (review, settings) => {
  requireConfig(settings)
  const proveedorId = positiveInteger(review?.proveedor_id)
  if (!proveedorId) {
    throw new TypeError('Seleccioná un proveedor válido.')
  }
  return {
    upload_token: requireString(review.upload_token, 'upload_token'),
    fecha_carga: requireDate(review.fecha_carga),
    hora_carga: review.hora_carga ? scalarText(review.hora_carga) : null,
    litros: requireNumber(review.litros, 'litros'),
    km_hora: requireInt(review.km_hora, 'km_hora'),
    equipo_id: positiveInteger(settings.equipoId),
    paniol_id: positiveInteger(review.paniol_id),
    proveedor_id: proveedorId,
    tipo_combustible_id: positiveInteger(review.tipo_combustible_id),
    remito: requireRemito(review.remito, 7),
    observaciones: scalarText(review.observaciones) || null,
  }
}

const buildRemitoPayload = (review, settings) => {
  requireConfig(settings)
  if (!positiveInteger(settings?.internoId)) {
    throw new TypeError('Falta el proveedor INTERNO. Contactá a soporte antes de confirmar.')
  }
  return {
    upload_token: requireString(review.upload_token, 'upload_token'),
    fecha_carga: requireDate(review.fecha_carga),
    hora_carga: review.hora_carga ? scalarText(review.hora_carga) : null,
    litros: requireNumber(review.litros, 'litros'),
    km_hora: requireNumber(review.km_hora, 'km_hora'),
    equipo_id: positiveInteger(settings.equipoId),
    paniol_id: positiveInteger(review.paniol_id),
    remito: requireRemito(review.remito, '6-7'),
    tipo_combustible_id: positiveInteger(review.tipo_combustible_id),
    observaciones: scalarText(review.observaciones) || null,
  }
}

const requireString = (value, field) => {
  const text = scalarText(value)
  if (!text) throw new TypeError(`${field} es obligatorio.`)
  return text
}

export const buildConfirmPayload = (review, settings, tipo) => {
  if (tipo === FUEL_TIPO_REMITO_INTERNO) return buildRemitoPayload(review, settings)
  return buildTicketPayload(review, settings)
}

const TRANSITIONS = {
  selecting: { PROCESS: 'processing' },
  processing: { ANALYZED: 'reviewing', FAIL: 'error' },
  reviewing: { CONFIRM: 'confirming', FAIL: 'error', RESET: 'selecting' },
  confirming: { CONFIRMED: 'success', FAIL: 'error' },
  success: { RESET: 'selecting' },
  error: { RETRY: 'processing', REVIEW: 'reviewing', RESET: 'selecting' },
}

export const transitionReviewState = (state, event) => {
  if (!TRANSITIONS[state]) throw new TypeError(`Estado desconocido: ${state}`)
  const next = TRANSITIONS[state][event]
  if (!next) throw new TypeError(`Transición no permitida: ${state} + ${event}`)
  return next
}
