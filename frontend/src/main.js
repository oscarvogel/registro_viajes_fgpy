import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import App from './App.vue'
import router from './router'
import loggerPlugin, { clientLogger } from './services/logger'
import * as Sentry from "@sentry/vue"
import { BrowserTracing } from "@sentry/tracing"
import axios from 'axios'
import { API_URL } from './config'
import { installAuthInterceptor } from './services/httpAuth'
import { activateWaitingWorker, canRegisterServiceWorker, checkForServiceWorkerUpdate } from './services/serviceWorkerRegistration'

const pinia = createPinia()
const app = createApp(App)

installAuthInterceptor(axios, { apiUrl: API_URL, clientLogger })

// Inicializar Sentry antes de montar la app
Sentry.init({
  app,
  dsn: import.meta.env.VITE_SENTRY_DSN,
  integrations: [new BrowserTracing({ routingInstrumentation: Sentry.vueRouterInstrumentation(router) })],
  environment: import.meta.env.VITE_SENTRY_ENV || 'production',
  release: import.meta.env.VITE_SENTRY_RELEASE || import.meta.env.VITE_APP_VERSION,
  tracesSampleRate: 0.05,
  ignoreErrors: [
    'ResizeObserver',
    'Script error.',
    'Non-Error promise rejection',
    'chrome-extension://',
    'moz-extension://',
    'Safari error',
    'Blocked by adblocker'
  ],
  beforeSend(event, hint) {
    // Ignorar errores sin stacktrace o provenientes de extensiones
    try {
      const exc = event.exception?.values?.[0]
      if (!exc || !exc.stacktrace) return null

      const message = (event.message || '').toString()
      if (message.includes('chrome-extension://') || message.includes('moz-extension://')) return null
    } catch (e) {
      // fallthrough
    }
    return event
  }
})

app.use(pinia)
app.use(router)
app.use(loggerPlugin) // Instalar logger

// Logging de navegaciÃ³n
router.beforeEach((to, from) => {
  if (from.name) {
    clientLogger.logNavigation(from.path, to.path)
  }
})

app.mount('#app')

// If the user is already authenticated (returned to app), set the clientLogger userId
try {
  const userJson = localStorage.getItem('user')
  if (userJson) {
    const user = JSON.parse(userJson)
    if (user && user.id) {
      clientLogger.setUserId(user.id)
    }
  }
} catch (e) {
  // ignore
}

if (canRegisterServiceWorker()) {
  let refreshingForUpdate = false

  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (refreshingForUpdate) return
    refreshingForUpdate = true
    window.location.reload()
  })

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then((registration) => {
        clientLogger.info('Service Worker registrado', { event_type: 'system' })

        activateWaitingWorker(registration)
        checkForServiceWorkerUpdate({ registration, clientLogger })

        registration.addEventListener('updatefound', () => {
          const newWorker = registration.installing
          if (!newWorker) return

          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              window.dispatchEvent(new Event('sw:update'))
              activateWaitingWorker(registration)
            }
          })
        })

        window.addEventListener('online', () => checkForServiceWorkerUpdate({ registration, clientLogger }))
        document.addEventListener('visibilitychange', () => {
          if (document.visibilityState === 'visible') {
            checkForServiceWorkerUpdate({ registration, clientLogger })
          }
        })
        window.setInterval(() => checkForServiceWorkerUpdate({ registration, clientLogger }), 15 * 60 * 1000)
      })
      .catch((error) => {
        clientLogger.error('Error registrando Service Worker', {
          event_type: 'system',
          error_name: error.name,
          error_message: error.message
        })
      })
  })
}
