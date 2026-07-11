export const getPendingRecordType = (record) => record?.record_type || 'viaje'

export const getPendingRecordEndpoint = (recordType) => {
  return recordType === 'carreton' ? '/movimiento-carreton' : '/registro-viaje'
}

export const resolveUsuario = ({ payload, clientLogger, storage = globalThis.localStorage }) => {
  if (payload.usuario) return payload.usuario
  if (clientLogger?.userId) return clientLogger.userId

  try {
    const userStr = storage?.getItem('user')
    if (userStr) {
      const user = JSON.parse(userStr)
      if (user?.id) return user.id
    }
  } catch (e) {
    // Ignore corrupt storage; caller will handle missing usuario.
  }

  return payload.chofer_id || null
}

export const preparePendingPayload = (record, { clientLogger, storage } = {}) => {
  const payload = { ...record }
  const recordType = getPendingRecordType(record)

  delete payload.local_id
  delete payload.synced
  delete payload.timestamp
  delete payload.record_type
  delete payload.blocked
  delete payload.blocked_reason
  delete payload.blocked_at

  if (payload.proveedor_id === '') delete payload.proveedor_id
  if (payload.cliente_id === '') delete payload.cliente_id

  if (payload.neto_origen) payload.neto_origen = Number(payload.neto_origen)
  if (payload.neto_destino) payload.neto_destino = Number(payload.neto_destino)
  if (payload.km_inicial !== undefined) payload.km_inicial = Number(payload.km_inicial)
  if (payload.km_final !== undefined) payload.km_final = Number(payload.km_final)
  if (payload.equipo_id !== undefined && payload.equipo_id !== '') payload.equipo_id = Number(payload.equipo_id)
  if (payload.unidad_negocio_id !== undefined && payload.unidad_negocio_id !== '') payload.unidad_negocio_id = Number(payload.unidad_negocio_id)

  if (payload.origen_carreton === null || payload.origen_carreton === undefined) payload.origen_carreton = ''
  if (payload.destino_carreton === null || payload.destino_carreton === undefined) payload.destino_carreton = ''

  payload.usuario = resolveUsuario({ payload, clientLogger, storage })

  return { payload, recordType, endpoint: getPendingRecordEndpoint(recordType) }
}

export const getHttpErrorStatus = (error) => error?.response?.status

export const getHttpErrorDetail = (error) => {
  return typeof error?.response?.data?.detail === 'string'
    ? error.response.data.detail
    : error?.message
}

export const recoverBlockedCarretonKmRecord = (record = {}) => {
  const recordType = getPendingRecordType(record)
  if (recordType !== 'carreton') return null

  const kmInicial = Number(String(record.km_inicial ?? '').replace(',', '.'))
  const kmFinal = Number(String(record.km_final ?? '').replace(',', '.'))
  if (!Number.isFinite(kmInicial) || !Number.isFinite(kmFinal) || kmFinal <= kmInicial) {
    return null
  }

  return {
    ...record,
    km_inicial: kmInicial,
    km_final: kmFinal,
    blocked: false,
    blocked_reason: undefined,
    blocked_at: undefined,
  }
}

export const syncOnePendingRecord = async ({
  record,
  apiUrl,
  httpClient,
  storage,
  clientLogger,
}) => {
  const { payload, recordType, endpoint } = preparePendingPayload(record, { clientLogger, storage })

  if (!payload.usuario) {
    return {
      ok: false,
      status: null,
      recordType,
      endpoint,
      blocked: true,
      authRequired: false,
      detail: 'Usuario faltante. Debe iniciar sesion y volver a cargar el registro.',
    }
  }

  try {
    const response = await httpClient.post(`${apiUrl}${endpoint}`, payload)
    return { ok: true, response, recordType, endpoint, payload }
  } catch (error) {
    const status = getHttpErrorStatus(error)
    return {
      ok: false,
      status,
      recordType,
      endpoint,
      blocked: recordType === 'carreton' && status === 400,
      authRequired: status === 401,
      detail: getHttpErrorDetail(error),
      error,
    }
  }
}
