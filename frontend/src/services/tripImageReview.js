const positiveInteger = (value) => {
  const number = typeof value === 'string' && /^\d+$/.test(value.trim()) ? Number(value) : value
  return Number.isInteger(number) && number > 0 ? number : null
}

const normalizedText = (value) => String(value ?? '').trim().toUpperCase().replace(/[^A-Z0-9]/g, '')
const scalarText = (value) => String(value ?? '').trim()
const active = (item) => item?.activo === true
const list = (value) => Array.isArray(value) ? value : []
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

export const readTripImageSettings = ({ storage, catalog = {} }) => {
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
  const activeClientIds = Object.freeze(list(catalog.clientes)
    .filter(active)
    .map((item) => positiveInteger(item.id))
    .filter(Boolean))
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
    activeClientIds,
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

const parseMillitons = (value) => {
  const text = String(value ?? '').trim().replace(',', '.')
  if (!WEIGHT_PATTERN.test(text)) throw new TypeError('El peso debe ser un decimal válido.')
  const [whole, decimals = ''] = text.split('.')
  const millitons = (Number(whole) * 1000) + Number(decimals.padEnd(3, '0'))
  if (!Number.isSafeInteger(millitons) || millitons < 0) throw new TypeError('El peso debe ser finito y no negativo.')
  return millitons
}

export const formatWeight = (value) => parseWeight(value).toFixed(3)

const observedValue = (proposal, ...names) => names.map((name) => proposal[name]).find((value) => value != null) ?? ''

export const createReviewModel = (analysis, settings, today) => {
  const proposal = analysis?.proposal || {}
  const warnings = [...list(proposal.warnings)]
  const configurationWarnings = []
  const observedPlate = observedValue(proposal, 'patente_observada', 'observed_plate', 'patente')
  const observedDriver = observedValue(proposal, 'chofer_observado', 'observed_driver', 'chofer')
  if (observedPlate && normalizedText(observedPlate) !== normalizedText(settings?.patente)) {
    configurationWarnings.push(
      `La foto parece indicar ${observedPlate}; en Ajustes figura ${settings?.patente || 'sin configurar'}.`,
    )
  }
  const userName = settings?.user?.nombre || ''
  const userSurname = settings?.user?.apellido || ''
  const configuredDriver = `${userSurname} ${userName}`.trim()
  const configuredDrivers = [normalizedText(`${userName} ${userSurname}`), normalizedText(`${userSurname} ${userName}`)]
  if (observedDriver && !configuredDrivers.includes(normalizedText(observedDriver))) {
    configurationWarnings.push(
      `La foto parece indicar ${observedDriver}; el usuario actual es ${configuredDriver || 'desconocido'}.`,
    )
  }
  const config = Object.freeze({
    user: userSnapshot(settings?.user),
    patente: settings?.patente || '',
    equipo: equipmentSnapshot(settings?.equipo),
    unidadNegocio: unitSnapshot(settings?.unidadNegocio),
  })
  return {
    upload_token: analysis?.upload_token,
    fecha_remision: proposal.fecha_remision || '',
    fecha_recepcion: today,
    numero_remision_fpv: proposal.numero_remision_fpv || '',
    cliente_id: proposal.cliente_id ?? null,
    cliente_candidato: proposal.cliente_candidato ?? null,
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
    configurationWarnings,
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
    && settings?.user?.activo === true
    && positiveInteger(settings.user.id) === userId
    && settings?.equipo?.activo === true
    && positiveInteger(settings.equipo.id) === equipoId
    && normalizedText(settings.equipo.patente) === normalizedText(settings.patente)
    && settings?.unidadNegocio?.activo === true
    && positiveInteger(settings.unidadNegocio.id) === unidadId
  if (!validConfig) {
    throw new TypeError('La configuración del viaje está incompleta.')
  }
  const brutoM = parseMillitons(review?.peso_bruto_destino)
  const taraM = parseMillitons(review?.tara_destino)
  const netoM = parseMillitons(review?.neto_destino)
  if (brutoM <= 0 || taraM < 0 || netoM <= 0) throw new TypeError('Los pesos bruto y neto deben ser mayores que cero.')
  if (Math.abs((brutoM - taraM) - netoM) > 10) throw new TypeError('Los pesos no cierran dentro de la tolerancia permitida.')
  if (!REMITO.test(String(review?.numero_remision_fpv))) throw new TypeError('El remito debe tener formato 000-000-0000000.')
  const clienteId = positiveInteger(review?.cliente_id)
  if (!clienteId || !Array.isArray(settings?.activeClientIds) || !settings.activeClientIds.includes(clienteId)) {
    throw new TypeError('Seleccioná un cliente activo válido.')
  }
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
    cliente_id: clienteId,
    proveedor_id: proveedorId,
    patente: settings.patente,
    unidad_negocio_id: settings.unidadNegocioId,
    peso_bruto_destino: brutoM / 1000,
    tara_destino: taraM / 1000,
    neto_destino: netoM / 1000,
    observaciones: String(review.observaciones ?? '').trim(),
  }
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
