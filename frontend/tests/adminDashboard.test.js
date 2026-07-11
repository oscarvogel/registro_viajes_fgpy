import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildAdminDashboardParams,
  buildDefaultAdminDashboardRange,
  fetchAdminDashboardSummary,
  normalizeAdminDashboardSummary,
} from '../src/services/adminDashboard.js'

test('builds monthly default dashboard range', () => {
  const range = buildDefaultAdminDashboardRange(new Date('2026-05-30T12:00:00Z'))

  assert.deepEqual(range, {
    fecha_desde: '2026-05-01',
    fecha_hasta: '2026-05-30',
  })
})

test('builds compact dashboard summary params', () => {
  assert.equal(
    buildAdminDashboardParams({ fecha_desde: '2026-05-01', fecha_hasta: '2026-05-30', unused: '' }),
    'fecha_desde=2026-05-01&fecha_hasta=2026-05-30'
  )
})

test('fetches admin dashboard summary from protected endpoint', async () => {
  const calls = []
  const data = { kpis: { viajes: 1 } }
  const httpClient = {
    get: async (url) => {
      calls.push(url)
      return { data }
    },
  }

  const result = await fetchAdminDashboardSummary({
    httpClient,
    apiUrl: '/api',
    filters: { fecha_desde: '2026-05-01', fecha_hasta: '2026-05-30' },
  })

  assert.equal(result, data)
  assert.deepEqual(calls, ['/api/admin/dashboard-summary?fecha_desde=2026-05-01&fecha_hasta=2026-05-30'])
})

test('normalizes missing dashboard sections to safe defaults', () => {
  const summary = normalizeAdminDashboardSummary({})

  assert.equal(summary.kpis.viajes, 0)
  assert.equal(summary.kpis.toneladas, 0)
  assert.deepEqual(summary.rankings.por_equipo, [])
  assert.equal(summary.alerts.blocked_records_note, '')
  assert.equal('client_log_items' in summary.alerts, false)
  assert.equal('errores_frontend' in summary.kpis, false)
})

test('normalizes selectable ranking summary details', () => {
  const summary = normalizeAdminDashboardSummary({
    rankings: {
      por_equipo: [{
        id: '10',
        kind: 'equipo',
        label: 'AAPV328',
        count: '25',
        total: '3565.95',
        average: '142.64',
        share: '57.65',
        units: [{ label: 'Transporte Carreton', count: '19', total: '3396' }],
        days: [{ fecha: '2026-05-10', count: '2', total: '125.5', average: '62.75' }],
        fuel_liters: '215.4',
        fuel_days: [{ fecha: '2026-05-11', litros: '100.4' }],
      }],
    },
  })

  assert.deepEqual(summary.rankings.por_equipo[0], {
    id: 10,
    kind: 'equipo',
    label: 'AAPV328',
    count: 25,
    total: 3565.95,
    average: 142.64,
    share: 57.65,
    units: [{ label: 'Transporte Carreton', count: 19, total: 3396 }],
    days: [{ fecha: '2026-05-10', count: 2, total: 125.5, average: 62.75 }],
    fuel_liters: 215.4,
    fuel_days: [{ fecha: '2026-05-11', litros: 100.4 }],
  })
})
