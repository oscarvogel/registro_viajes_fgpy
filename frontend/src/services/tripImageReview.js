const positiveInteger = (value) => {
  const number = typeof value === 'string' && /^\d+$/.test(value.trim()) ? Number(value) : value
  return Number.isInteger(number) && number > 0 ? number : null
}

const normalizedText = (value) => String(value ?? '').trim().toUpperCase().replace(/[^A-Z0-9]/g, '')
const active = (item) => item && item.activo !== false && item.active !== false
const list = (value) => Array.isArray(value) ? value : []
const frozenCopy = (value) => value ? Object.freeze({ ...value }) : null

export const readTripImageSettings = ({ storage, catalog = {} }) => {
  const errors = []
  let userId = null
  try {
    userId = positiveInteger(JSON.parse(storage?.getItem('user') ?? 'null')?.id)
  } catch {
    errors.push('La sesión guardada no es válida.')
  }

  const patente = String(storage?.getItem('default_patente') ?? '').trim().toUpperCase()
  const unidadNegocioId = positiveInteger(storage?.getItem('default_unidad_negocio'))
  if (!unidadNegocioId && storage?.getItem('default_unidad_negocio')) errors.push('La unidad de negocio guardada no es válida.')

  const user = frozenCopy(list(catalog.empleados).find((item) => active(item) && positiveInteger(item.id) === userId))
  const equipo = frozenCopy(list(catalog.equipos).find((item) => active(item) && normalizedText(item.patente) === normalizedText(patente)))
  const unidadNegocio = frozenCopy(list(catalog.unidadesNegocio).find((item) => active(item) && positiveInteger(item.id) === unidadNegocioId))
  const activeProviderIds = Object.freeze(list(catalog.proveedores)
    .filter(active)
    .map((item) => positiveInteger(item.id))
    .filter(Boolean))
  const missing = []
  if (!user) missing.push('user')
  if (!patente || !equipo) missing.push('patente')
  if (!unidadNegocio) missing.push('unidad_negocio')
  return Object.freeze({
    userId: user ? positiveInteger(user.id) : null,
    user,
    patente,
    equipoId: equipo ? positiveInteger(equipo.id) : null,
    equipo,
    unidadNegocioId: unidadNegocio ? positiveInteger(unidadNegocio.id) : null,
    unidadNegocio,
    activeProviderIds,
    missing: Object.freeze(missing),
    errors: Object.freeze(errors),
    complete: missing.length === 0,
  })
}

const WEIGHT_PATTERN = /^\d+(?:[.,]\d{1,3})?$/

export const parseWeight = (value) => {
  const text = String(value ?? '').trim()
  if (!WEIGHT_PATTERN.test(text)) throw new TypeError('El peso debe ser un decimal válido.')
  const number = Number(text.replace(',', '.'))
  if (!Number.isFinite(number) || number < 0) throw new TypeError('El peso debe ser finito y no negativo.')
  return number
}

export const formatWeight = (value) => parseWeight(value).toFixed(3)

const observedValue = (proposal, ...names) => names.map((name) => proposal[name]).find((value) => value != null) ?? ''

export const createReviewModel = (analysis, settings, today) => {
  const proposal = analysis?.proposal || {}
  const warnings = [...list(proposal.warnings)]
  const observedPlate = observedValue(proposal, 'patente_observada', 'observed_plate', 'patente')
  const observedDriver = observedValue(proposal, 'chofer_observado', 'observed_driver', 'chofer')
  if (observedPlate && normalizedText(observedPlate) !== normalizedText(settings?.patente)) {
    warnings.push('La patente observada no coincide con la configuración actual.')
  }
  const configuredDriver = settings?.user?.nombre || settings?.user?.name || ''
  if (observedDriver && normalizedText(observedDriver) !== normalizedText(configuredDriver)) {
    warnings.push('El chofer observado no coincide con el usuario actual.')
  }
  const config = Object.freeze({
    user: frozenCopy(settings?.user),
    patente: settings?.patente || '',
    equipo: frozenCopy(settings?.equipo),
    unidadNegocio: frozenCopy(settings?.unidadNegocio),
  })
  return {
    upload_token: analysis?.upload_token,
    fecha_remision: proposal.fecha_remision || '',
    fecha_recepcion: today,
    numero_remision_fpv: proposal.numero_remision_fpv || '',
    proveedor_id: proposal.proveedor_id ?? null,
    proveedor_candidato: proposal.proveedor_candidato ?? null,
    peso_bruto_destino: formatWeight(proposal.peso_bruto_destino),
    tara_destino: formatWeight(proposal.tara_destino),
    neto_destino: formatWeight(proposal.neto_destino),
    observaciones: '',
    config,
    observed: { patente: observedPlate, chofer: observedDriver },
    confidence: proposal.confidence ?? null,
    warnings,
  }
}

const ISO_DATE = /^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$/
const REMITO = /^\d{3}-\d{3}-\d{7}$/

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

export const buildConfirmPayload = (review, settings) => {
  const userId = positiveInteger(settings?.userId)
  const equipoId = positiveInteger(settings?.equipoId)
  const unidadId = positiveInteger(settings?.unidadNegocioId)
  const validConfig = userId
    && equipoId
    && unidadId
    && active(settings?.user)
    && positiveInteger(settings.user.id) === userId
    && active(settings?.equipo)
    && positiveInteger(settings.equipo.id) === equipoId
    && normalizedText(settings.equipo.patente) === normalizedText(settings.patente)
    && active(settings?.unidadNegocio)
    && positiveInteger(settings.unidadNegocio.id) === unidadId
  if (!validConfig) {
    throw new TypeError('La configuración del viaje está incompleta.')
  }
  const bruto = parseWeight(review?.peso_bruto_destino)
  const tara = parseWeight(review?.tara_destino)
  const neto = parseWeight(review?.neto_destino)
  if (bruto <= 0 || tara < 0 || neto <= 0) throw new TypeError('Los pesos bruto y neto deben ser mayores que cero.')
  if (Math.abs(bruto - tara - neto) > 0.01 + Number.EPSILON) throw new TypeError('Los pesos no cierran dentro de la tolerancia permitida.')
  if (!REMITO.test(String(review?.numero_remision_fpv))) throw new TypeError('El remito debe tener formato 000-000-0000000.')
  const proveedorId = positiveInteger(review?.proveedor_id)
  if (!proveedorId || !Array.isArray(settings?.activeProviderIds) || !settings.activeProviderIds.includes(proveedorId)) {
    throw new TypeError('Seleccioná un proveedor activo válido.')
  }
  const uploadToken = typeof review?.upload_token === 'string' ? review.upload_token.trim() : ''
  if (!uploadToken) throw new TypeError('La imagen analizada ya no está disponible.')
  return {
    upload_token: uploadToken,
    fecha_remision: requireDate(review.fecha_remision),
    fecha_recepcion: requireDate(review.fecha_recepcion),
    numero_remision_fpv: review.numero_remision_fpv,
    proveedor_id: proveedorId,
    patente: settings.patente,
    unidad_negocio_id: settings.unidadNegocioId,
    peso_bruto_destino: bruto,
    tara_destino: tara,
    neto_destino: neto,
    observaciones: String(review.observaciones ?? '').trim(),
  }
}

const TRANSITIONS = {
  selecting: { PROCESS: 'processing' },
  processing: { ANALYZED: 'reviewing', FAIL: 'error' },
  reviewing: { CONFIRM: 'confirming', FAIL: 'error', RESET: 'selecting' },
  confirming: { CONFIRMED: 'success', FAIL: 'error' },
  success: { RESET: 'selecting' },
  error: { RETRY: 'processing', RESET: 'selecting' },
}

export const transitionReviewState = (state, event) => {
  if (!TRANSITIONS[state]) throw new TypeError(`Estado desconocido: ${state}`)
  const next = TRANSITIONS[state][event]
  if (!next) throw new TypeError(`Transición no permitida: ${state} + ${event}`)
  return next
}
