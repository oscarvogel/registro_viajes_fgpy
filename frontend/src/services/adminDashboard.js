const toIsoDate = (date) => date.toISOString().split('T')[0]

export const buildDefaultAdminDashboardRange = (now = new Date()) => {
  const firstDay = new Date(now.getFullYear(), now.getMonth(), 1)
  return {
    fecha_desde: toIsoDate(firstDay),
    fecha_hasta: toIsoDate(now),
  }
}

export const buildAdminDashboardParams = (filters = {}) => {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    const normalizedValue = String(value || '').trim()
    if (normalizedValue) params.set(key, normalizedValue)
  })
  return params.toString()
}

export const fetchAdminDashboardSummary = async ({ httpClient, apiUrl, filters = {} }) => {
  const query = buildAdminDashboardParams(filters)
  const url = `${apiUrl}/admin/dashboard-summary${query ? `?${query}` : ''}`
  const response = await httpClient.get(url)
  return response.data
}

const toNumber = (value) => Number(value || 0)

const normalizeDaySummary = (day = {}) => ({
  ...day,
  count: toNumber(day.count),
  total: toNumber(day.total),
  average: toNumber(day.average),
})

const normalizeFuelDaySummary = (day = {}) => ({
  ...day,
  litros: toNumber(day.litros),
})

const normalizeUnitSummary = (unit = {}) => ({
  ...unit,
  count: toNumber(unit.count),
  total: toNumber(unit.total),
})

const normalizeRankingItem = (item = {}) => ({
  ...item,
  id: toNumber(item.id),
  count: toNumber(item.count),
  total: toNumber(item.total),
  average: toNumber(item.average),
  share: toNumber(item.share),
  units: Array.isArray(item.units) ? item.units.map(normalizeUnitSummary) : [],
  days: Array.isArray(item.days) ? item.days.map(normalizeDaySummary) : [],
  fuel_liters: toNumber(item.fuel_liters),
  fuel_days: Array.isArray(item.fuel_days) ? item.fuel_days.map(normalizeFuelDaySummary) : [],
})

const normalizeRanking = (items) => Array.isArray(items) ? items.map(normalizeRankingItem) : []

export const normalizeAdminDashboardSummary = (summary = {}) => {
  const kpis = {
    viajes: Number(summary.kpis?.viajes || 0),
    toneladas: Number(summary.kpis?.toneladas || 0),
    promedio_toneladas_por_viaje: Number(summary.kpis?.promedio_toneladas_por_viaje || 0),
    litros: Number(summary.kpis?.litros || 0),
    movimientos_carreton: Number(summary.kpis?.movimientos_carreton || 0),
  }

  if ('errores_frontend' in (summary.kpis || {})) kpis.errores_frontend = toNumber(summary.kpis.errores_frontend)
  if ('warnings_frontend' in (summary.kpis || {})) kpis.warnings_frontend = toNumber(summary.kpis.warnings_frontend)

  const alerts = {
    blocked_records_note: summary.alerts?.blocked_records_note || '',
  }

  if ('client_log_items' in (summary.alerts || {})) alerts.client_log_items = toNumber(summary.alerts.client_log_items)

  return {
    period: summary.period || {},
    kpis,
    rankings: {
      por_equipo: normalizeRanking(summary.rankings?.por_equipo),
      por_chofer: normalizeRanking(summary.rankings?.por_chofer),
      por_unidad_negocio: normalizeRanking(summary.rankings?.por_unidad_negocio),
    },
    alerts,
  }
}
