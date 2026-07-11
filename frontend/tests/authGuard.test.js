import assert from 'node:assert/strict'
import test from 'node:test'
import { resolveAuthNavigation } from '../src/router/authGuard.js'

const createStorage = (initial = {}) => {
  const values = new Map(Object.entries(initial))
  return {
    getItem: (key) => values.has(key) ? values.get(key) : null,
    removeItem: (key) => values.delete(key),
    has: (key) => values.has(key),
  }
}

test('protected routes redirect to login without a stored session', () => {
  const result = resolveAuthNavigation(
    { path: '/new-trip', fullPath: '/new-trip?x=1', meta: { requiresAuth: true } },
    createStorage()
  )

  assert.deepEqual(result, {
    path: '/login',
    query: { redirect: '/new-trip?x=1' },
  })
})

test('protected routes continue with a stored session', () => {
  const result = resolveAuthNavigation(
    { path: '/new-trip', fullPath: '/new-trip', meta: { requiresAuth: true } },
    createStorage({ token: 'jwt', user: JSON.stringify({ id: 123 }) })
  )

  assert.equal(result, true)
})

test('admin routes redirect non-admin users to settings', () => {
  const result = resolveAuthNavigation(
    { path: '/admin/logs', fullPath: '/admin/logs', meta: { requiresAuth: true, requiresAdmin: true } },
    createStorage({ token: 'jwt', user: JSON.stringify({ id: 123 }) }),
    [63]
  )

  assert.equal(result, '/settings')
})

test('admin routes continue for configured admin users', () => {
  const result = resolveAuthNavigation(
    { path: '/admin/logs', fullPath: '/admin/logs', meta: { requiresAuth: true, requiresAdmin: true } },
    createStorage({ token: 'jwt', user: JSON.stringify({ id: 63 }) }),
    [63]
  )

  assert.equal(result, true)
})

test('admin dashboard route uses the same admin guard contract', () => {
  const result = resolveAuthNavigation(
    { path: '/admin/dashboard', fullPath: '/admin/dashboard', meta: { requiresAuth: true, requiresAdmin: true } },
    createStorage({ token: 'jwt', user: JSON.stringify({ id: 63 }) }),
    [63]
  )

  assert.equal(result, true)
})

test('login route redirects authenticated users to dashboard by default', () => {
  const result = resolveAuthNavigation(
    { path: '/login', fullPath: '/login', meta: { hideNavbar: true } },
    createStorage({ token: 'jwt', user: JSON.stringify({ id: 123 }) })
  )

  assert.equal(result, '/dashboard')
})

test('login route redirects authenticated users to safe redirect query', () => {
  const result = resolveAuthNavigation(
    { path: '/login', fullPath: '/login?redirect=/history', query: { redirect: '/history' }, meta: { hideNavbar: true } },
    createStorage({ token: 'jwt', user: JSON.stringify({ id: 123 }) })
  )

  assert.equal(result, '/history')
})

test('login route ignores unsafe redirect query', () => {
  const result = resolveAuthNavigation(
    { path: '/login', fullPath: '/login?redirect=https://example.com', query: { redirect: 'https://example.com' }, meta: { hideNavbar: true } },
    createStorage({ token: 'jwt', user: JSON.stringify({ id: 123 }) })
  )

  assert.equal(result, '/dashboard')
})

test('corrupt stored user redirects and clears session', () => {
  const storage = createStorage({ token: 'jwt', user: '{bad-json' })

  const result = resolveAuthNavigation(
    { path: '/history', fullPath: '/history', meta: { requiresAuth: true } },
    storage
  )

  assert.deepEqual(result, {
    path: '/login',
    query: { redirect: '/history' },
  })
  assert.equal(storage.has('token'), false)
  assert.equal(storage.has('user'), false)
})
