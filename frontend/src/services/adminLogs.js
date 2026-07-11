export const buildClientLogSummaryParams = (filters = {}) => {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    const normalizedValue = String(value || '').trim()
    if (normalizedValue) params.set(key, normalizedValue)
  })
  return params.toString()
}

export const fetchClientLogSummary = async ({ httpClient, apiUrl, filters = {} }) => {
  const query = buildClientLogSummaryParams(filters)
  const url = `${apiUrl}/admin/client-log-summary${query ? `?${query}` : ''}`
  const response = await httpClient.get(url)
  return response.data
}

export const clearClientLogSummary = async ({ httpClient, apiUrl, filters = {} }) => {
  const query = buildClientLogSummaryParams(filters)
  const url = `${apiUrl}/admin/client-log-summary${query ? `?${query}` : ''}`
  const response = await httpClient.delete(url)
  return response.data
}

export const hasActiveClientLogFilters = (filters = {}) => {
  return Object.values(filters).some((value) => String(value || '').trim())
}

export const getCategoryEntries = (summary = {}) => {
  return Object.entries(summary.categories || {}).sort((left, right) => right[1] - left[1])
}

export const buildClientLogExportPayload = ({ data = {}, filters = {} }) => ({
  exported_at: new Date().toISOString(),
  filters: Object.fromEntries(
    Object.entries(filters).filter(([, value]) => String(value || '').trim())
  ),
  count: data.count || 0,
  max_items: data.max_items || 0,
  items: data.items || [],
})

const escapeCsvValue = (value) => {
  const text = value === undefined || value === null ? '' : String(value)
  return `"${text.replaceAll('"', '""')}"`
}

export const buildClientLogCsv = (items = []) => {
  const rows = [
    ['timestamp', 'category', 'errors', 'warnings', 'page', 'component', 'message', 'error_name', 'error_message', 'suggested_actions'],
  ]

  items.forEach((item) => {
    const categories = getCategoryEntries(item.summary).map(([category, count]) => `${category}:${count}`).join('; ')
    const actions = (item.suggested_actions || []).join(' | ')
    const samples = item.samples?.length ? item.samples : [{}]
    samples.forEach((sample) => {
      rows.push([
        item.timestamp || '',
        categories,
        item.summary?.errors || 0,
        item.summary?.warnings || 0,
        sample.page || '',
        sample.component || '',
        sample.message || '',
        sample.error_name || '',
        sample.error_message || '',
        actions,
      ])
    })
  })

  return rows.map((row) => row.map(escapeCsvValue).join(',')).join('\n')
}
