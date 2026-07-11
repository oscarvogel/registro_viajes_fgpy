import axios from 'axios'
import { API_URL } from '../config'
import { safeConsole } from './safeConsole'

const MAX_QUEUE_SIZE = 100

const normalizeExtra = (extra = {}) => {
  if (!extra || typeof extra !== 'object') return {}
  return { ...extra }
}

class ClientLogger {
  constructor({ apiUrl = API_URL, httpClient = axios } = {}) {
    this.apiUrl = apiUrl
    this.httpClient = httpClient
    this.queue = []
    this.userId = null
    this.flushing = false
  }

  setUserId(userId) {
    this.userId = userId
    this.info('Usuario autenticado', {
      event_type: 'auth',
      user_id: userId,
    })
  }

  clearUserId() {
    this.userId = null
  }

  createEntry(level, message, data = {}) {
    return {
      level,
      message: String(message || ''),
      timestamp: new Date().toISOString(),
      url: globalThis.location?.href || '',
      user_agent: globalThis.navigator?.userAgent || '',
      user_id: data.user_id ?? this.userId ?? null,
      event_type: data.event_type || 'frontend',
      extra: normalizeExtra(data.extra || data),
      error_name: data.error_name,
      error_message: data.error_message,
    }
  }

  push(level, message, data = {}) {
    const entry = this.createEntry(level, message, data)
    this.queue.push(entry)
    if (this.queue.length > MAX_QUEUE_SIZE) {
      this.queue.splice(0, this.queue.length - MAX_QUEUE_SIZE)
    }
    return entry
  }

  debug(message, data = {}) {
    safeConsole.debug(message, data)
    return this.push('debug', message, data)
  }

  info(message, data = {}) {
    safeConsole.info(message, data)
    return this.push('info', message, data)
  }

  warning(message, data = {}) {
    safeConsole.warn(message, data)
    return this.push('warning', message, data)
  }

  error(message, data = {}) {
    safeConsole.error(message, data)
    return this.push('error', message, data)
  }

  logNavigation(from, to) {
    return this.info('Navegacion', {
      event_type: 'navigation',
      extra: { from, to },
    })
  }

  async flush() {
    if (this.flushing || this.queue.length === 0) return false

    this.flushing = true
    const logs = [...this.queue]

    try {
      await this.httpClient.post(`${this.apiUrl}/logs/client`, { logs })
      this.queue.splice(0, logs.length)
      return true
    } catch (error) {
      safeConsole.warn('Error enviando logs', error?.message || error)
      return false
    } finally {
      this.flushing = false
    }
  }
}

export const clientLogger = new ClientLogger()

export const createClientLogger = (options) => new ClientLogger(options)

export default {
  install(app) {
    app.config.globalProperties.$logger = clientLogger
  },
}
