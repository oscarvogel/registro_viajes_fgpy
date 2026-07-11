import assert from 'node:assert/strict'
import test from 'node:test'
import { clearStoredSession, getStoredSession, hasStoredSession } from '../src/services/session.js'

const createStorage = (initial = {}) => {
  const values = new Map(Object.entries(initial))
  return {
    getItem: (key) => values.has(key) ? values.get(key) : null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
    has: (key) => values.has(key),
  }
}

test('hasStoredSession requires token and user id', () => {
  assert.equal(hasStoredSession(createStorage()), false)
  assert.equal(hasStoredSession(createStorage({ token: 'jwt' })), false)
  assert.equal(hasStoredSession(createStorage({ user: JSON.stringify({ id: 123 }) })), false)
  assert.equal(hasStoredSession(createStorage({ token: 'jwt', user: JSON.stringify({ id: 123 }) })), true)
})

test('getStoredSession returns token and user when storage is valid', () => {
  const storage = createStorage({ token: 'jwt', user: JSON.stringify({ id: 123, nombre: 'Ada' }) })

  assert.deepEqual(getStoredSession(storage), {
    token: 'jwt',
    user: { id: 123, nombre: 'Ada' },
  })
})

test('invalid user JSON clears session and returns null', () => {
  const storage = createStorage({ token: 'jwt', user: '{bad-json' })

  assert.equal(getStoredSession(storage), null)
  assert.equal(storage.has('token'), false)
  assert.equal(storage.has('user'), false)
})

test('clearStoredSession removes token and user', () => {
  const storage = createStorage({ token: 'jwt', user: JSON.stringify({ id: 123 }) })

  clearStoredSession(storage)

  assert.equal(storage.has('token'), false)
  assert.equal(storage.has('user'), false)
})
