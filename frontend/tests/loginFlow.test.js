import assert from 'node:assert/strict'
import test from 'node:test'
import {
  getLoginErrorMessage,
  loginAndNavigate,
  resolveLoginRedirect,
  storeLoginSession,
} from '../src/services/loginFlow.js'

const createStorage = () => {
  const values = new Map()
  return {
    getItem: (key) => values.has(key) ? values.get(key) : null,
    setItem: (key, value) => values.set(key, value),
    has: (key) => values.has(key),
  }
}

test('storeLoginSession stores token and user', () => {
  const storage = createStorage()

  storeLoginSession({ access_token: 'jwt', user: { id: 123, nombre: 'Ada' } }, storage)

  assert.equal(storage.getItem('token'), 'jwt')
  assert.equal(storage.getItem('user'), JSON.stringify({ id: 123, nombre: 'Ada' }))
})

test('loginAndNavigate stores session, logs user and navigates on success', async () => {
  const storage = createStorage()
  const calls = []
  const httpClient = {
    post: async (url, body) => {
      calls.push({ url, body })
      return { data: { access_token: 'jwt', user: { id: 123 } } }
    },
  }
  const router = {
    pushed: null,
    push: async (path) => {
      router.pushed = path
    },
  }
  const clientLogger = {
    userId: null,
    setUserId: (id) => {
      clientLogger.userId = id
    },
  }

  const result = await loginAndNavigate({
    dni: '12345678',
    apiUrl: 'https://viajes.forestalparaguay.com/api',
    httpClient,
    storage,
    router,
    clientLogger,
  })

  assert.equal(result.ok, true)
  assert.deepEqual(calls, [{
    url: 'https://viajes.forestalparaguay.com/api/login',
    body: { documento: '12345678' },
  }])
  assert.equal(storage.getItem('token'), 'jwt')
  assert.equal(storage.getItem('user'), JSON.stringify({ id: 123 }))
  assert.equal(clientLogger.userId, 123)
  assert.equal(router.pushed, '/new-trip')
})

test('loginAndNavigate still navigates if afterLogin fails', async () => {
  const storage = createStorage()
  const httpClient = {
    post: async () => ({ data: { access_token: 'jwt', user: { id: 123 } } }),
  }
  const router = {
    pushed: null,
    push: async (path) => {
      router.pushed = path
    },
  }

  const result = await loginAndNavigate({
    dni: '12345678',
    apiUrl: '/api',
    httpClient,
    storage,
    router,
    afterLogin: async () => {
      throw new Error('version check failed')
    },
  })

  assert.equal(result.ok, true)
  assert.equal(router.pushed, '/new-trip')
  assert.equal(storage.getItem('token'), 'jwt')
})

test('loginAndNavigate respects safe redirect target', async () => {
  const storage = createStorage()
  const httpClient = {
    post: async () => ({ data: { access_token: 'jwt', user: { id: 123 } } }),
  }
  const router = {
    pushed: null,
    push: async (path) => {
      router.pushed = path
    },
  }

  const result = await loginAndNavigate({
    dni: '12345678',
    apiUrl: '/api',
    httpClient,
    storage,
    router,
    redirectTo: '/history?tab=fuel',
  })

  assert.equal(result.ok, true)
  assert.equal(router.pushed, '/history?tab=fuel')
})

test('resolveLoginRedirect rejects unsafe redirects', () => {
  assert.equal(resolveLoginRedirect('/history'), '/history')
  assert.equal(resolveLoginRedirect('https://example.com'), '/new-trip')
  assert.equal(resolveLoginRedirect('//example.com'), '/new-trip')
  assert.equal(resolveLoginRedirect('/login?redirect=/history'), '/new-trip')
  assert.equal(resolveLoginRedirect(''), '/new-trip')
})

test('loginAndNavigate returns backend error and does not store session on failure', async () => {
  const storage = createStorage()
  const httpClient = {
    post: async () => {
      throw { response: { data: { detail: 'Credenciales invÃ¡lidas' } } }
    },
  }
  const router = {
    push: async () => {
      throw new Error('should not navigate')
    },
  }

  const result = await loginAndNavigate({
    dni: '00000000',
    apiUrl: '/api',
    httpClient,
    storage,
    router,
  })

  assert.deepEqual(result, { ok: false, error: 'Credenciales invÃ¡lidas' })
  assert.equal(storage.has('token'), false)
  assert.equal(storage.has('user'), false)
})

test('loginAndNavigate returns rate-limit error without storing session', async () => {
  const storage = createStorage()
  const httpClient = {
    post: async () => {
      throw { response: { data: { detail: 'Demasiados intentos. Intente nuevamente mÃ¡s tarde.' } } }
    },
  }

  const result = await loginAndNavigate({
    dni: '00000000',
    apiUrl: '/api',
    httpClient,
    storage,
    router: { push: async () => {} },
  })

  assert.deepEqual(result, { ok: false, error: 'Demasiados intentos. Intente nuevamente mÃ¡s tarde.' })
  assert.equal(storage.has('token'), false)
})

test('getLoginErrorMessage falls back to generic message', () => {
  assert.equal(getLoginErrorMessage({}), 'Error de ingreso. Verifique DNI.')
})
