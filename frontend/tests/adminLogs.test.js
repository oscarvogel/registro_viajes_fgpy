import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildClientLogCsv,
  buildClientLogExportPayload,
  buildClientLogSummaryParams,
  clearClientLogSummary,
  fetchClientLogSummary,
  getCategoryEntries,
  hasActiveClientLogFilters,
} from '../src/services/adminLogs.js'

test('fetches client log summary from admin endpoint', async () => {
  const calls = []
  const data = { items: [], count: 0 }
  const httpClient = {
    get: async (url) => {
      calls.push(url)
      return { data }
    },
  }

  const result = await fetchClientLogSummary({ httpClient, apiUrl: 'https://example.test/api' })

  assert.equal(result, data)
  assert.deepEqual(calls, ['https://example.test/api/admin/client-log-summary'])
})

test('fetches client log summary with compact filters', async () => {
  const calls = []
  const httpClient = {
    get: async (url) => {
      calls.push(url)
      return { data: { items: [] } }
    },
  }

  await fetchClientLogSummary({
    httpClient,
    apiUrl: '/api',
    filters: { category: 'server', page: ' fuel ', date_from: '2026-05-24', date_to: '' },
  })

  assert.deepEqual(calls, ['/api/admin/client-log-summary?category=server&page=fuel&date_from=2026-05-24'])
})

test('builds empty query for blank log filters', () => {
  assert.equal(buildClientLogSummaryParams({ category: '', page: '   ' }), '')
})

test('clears client log summary through admin endpoint', async () => {
  const calls = []
  const data = { cleared: 3 }
  const httpClient = {
    delete: async (url) => {
      calls.push(url)
      return { data }
    },
  }

  const result = await clearClientLogSummary({ httpClient, apiUrl: '/api' })

  assert.equal(result, data)
  assert.deepEqual(calls, ['/api/admin/client-log-summary'])
})

test('clears client log summary with filters', async () => {
  const calls = []
  const httpClient = {
    delete: async (url) => {
      calls.push(url)
      return { data: { cleared: 1 } }
    },
  }

  const result = await clearClientLogSummary({
    httpClient,
    apiUrl: '/api',
    filters: { category: 'server', page: 'fuel' },
  })

  assert.equal(result.cleared, 1)
  assert.deepEqual(calls, ['/api/admin/client-log-summary?category=server&page=fuel'])
})

test('detects active client log filters', () => {
  assert.equal(hasActiveClientLogFilters({ category: '', page: '  ' }), false)
  assert.equal(hasActiveClientLogFilters({ category: 'server', page: '' }), true)
})

test('sorts category entries by descending count', () => {
  assert.deepEqual(getCategoryEntries({ categories: { navigation: 1, api: 5, ui: 3 } }), [
    ['api', 5],
    ['ui', 3],
    ['navigation', 1],
  ])
  assert.deepEqual(getCategoryEntries(), [])
})

test('builds sanitized export payload from current filtered data', () => {
  const data = { count: 1, max_items: 200, items: [{ timestamp: '2026-05-24T10:00:00', samples: [] }] }
  const payload = buildClientLogExportPayload({
    data,
    filters: { category: 'server', page: '', date_from: '2026-05-24' },
  })

  assert.equal(payload.count, 1)
  assert.equal(payload.items, data.items)
  assert.deepEqual(payload.filters, { category: 'server', date_from: '2026-05-24' })
  assert.match(payload.exported_at, /^\d{4}-\d{2}-\d{2}T/)
})

test('builds csv rows from log items and escapes values', () => {
  const csv = buildClientLogCsv([
    {
      timestamp: '2026-05-24T10:00:00',
      summary: { errors: 1, warnings: 0, categories: { server: 1 } },
      suggested_actions: ['Revisar backend'],
      samples: [
        {
          page: '/fuel-load',
          component: 'FuelLoad',
          message: 'HTTP "500"',
          error_name: 'HttpError',
          error_message: 'fallo',
        },
      ],
    },
  ])

  assert.match(csv, /^"timestamp","category","errors"/)
  assert.match(csv, /"server:1"/)
  assert.match(csv, /"HTTP ""500"""/)
  assert.match(csv, /"Revisar backend"/)
})
