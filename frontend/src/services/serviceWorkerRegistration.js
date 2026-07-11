export const canRegisterServiceWorker = ({
  navigatorRef = globalThis.navigator,
  env = import.meta.env,
} = {}) => {
  return Boolean(env?.PROD && navigatorRef && 'serviceWorker' in navigatorRef)
}

export const activateWaitingWorker = (registration) => {
  if (!registration?.waiting) return false

  try {
    registration.waiting.postMessage({ type: 'SKIP_WAITING' })
    return true
  } catch (e) {
    return false
  }
}

export const DEFAULT_SW_UPDATE_WARNING_THROTTLE_MS = 6 * 60 * 60 * 1000

let swUpdateFailureLastReportedAt = 0

export const resetServiceWorkerUpdateFailureThrottle = () => {
  swUpdateFailureLastReportedAt = 0
}

export const shouldReportServiceWorkerUpdateFailure = ({
  now = Date.now(),
  lastReportedAt = swUpdateFailureLastReportedAt,
  throttleMs = DEFAULT_SW_UPDATE_WARNING_THROTTLE_MS,
} = {}) => {
  return !lastReportedAt || now - lastReportedAt >= throttleMs
}

export const reportServiceWorkerUpdateFailure = ({
  error,
  clientLogger = null,
  now = Date.now(),
  throttleMs = DEFAULT_SW_UPDATE_WARNING_THROTTLE_MS,
} = {}) => {
  if (!shouldReportServiceWorkerUpdateFailure({ now, throttleMs })) {
    return false
  }

  swUpdateFailureLastReportedAt = now
  clientLogger?.warning?.('No se pudo verificar actualizacion del Service Worker', {
    event_type: 'system',
    extra: {
      reason: error?.message || String(error || 'unknown'),
      name: error?.name || 'Error',
    },
  })
  return true
}

export const checkForServiceWorkerUpdate = async ({
  registration,
  dispatchUpdate = () => globalThis.window?.dispatchEvent?.(new Event('sw:update')),
  clientLogger = null,
} = {}) => {
  if (!registration || typeof registration.update !== 'function') return false

  try {
    await registration.update()
    if (activateWaitingWorker(registration)) {
      dispatchUpdate()
      return true
    }
  } catch (error) {
    reportServiceWorkerUpdateFailure({ error, clientLogger })
  }

  return false
}
