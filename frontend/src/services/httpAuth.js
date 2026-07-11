import { clearStoredSession } from './session.js'

export const isApiRequest = (requestUrl = '', apiUrl = '') => {
  return Boolean(requestUrl && (requestUrl.startsWith(apiUrl) || requestUrl.startsWith('/api')))
}

export const addAuthorizationHeader = (config, token) => {
  if (!token) return config

  config.headers = config.headers || {}
  config.headers.Authorization = `Bearer ${token}`
  return config
}

export const createAuthRequestInterceptor = ({ apiUrl, storage = globalThis.localStorage }) => {
  return (config) => {
    try {
      const token = storage?.getItem('token')
      const requestUrl = config.url || ''

      if (token && isApiRequest(requestUrl, apiUrl)) {
        return addAuthorizationHeader(config, token)
      }
    } catch (e) {
      // Continue without auth header if localStorage is unavailable.
    }

    return config
  }
}

export const createUnauthorizedResponseHandler = ({
  storage = globalThis.localStorage,
  location = globalThis.location,
  clientLogger = null,
} = {}) => {
  return (error) => {
    if (error?.response?.status === 401) {
      clearStoredSession(storage)
      clientLogger?.clearUserId?.()

      if (location && location.pathname !== '/login') {
        location.href = '/login'
      }
    }

    return Promise.reject(error)
  }
}

export const installAuthInterceptor = (axiosInstance, options) => {
  const requestInterceptor = axiosInstance.interceptors.request.use(createAuthRequestInterceptor(options))
  const responseInterceptor = axiosInstance.interceptors.response.use(
    (response) => response,
    createUnauthorizedResponseHandler(options)
  )

  return { requestInterceptor, responseInterceptor }
}
