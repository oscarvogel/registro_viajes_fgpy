export const clearStoredSession = (storage = globalThis.localStorage) => {
  storage?.removeItem('token')
  storage?.removeItem('user')
}

export const getStoredSession = (storage = globalThis.localStorage) => {
  try {
    const token = storage?.getItem('token')
    const user = JSON.parse(storage?.getItem('user') || 'null')

    if (!token || !user?.id) {
      return null
    }

    return { token, user }
  } catch (e) {
    clearStoredSession(storage)
    return null
  }
}

export const hasStoredSession = (storage = globalThis.localStorage) => {
  return Boolean(getStoredSession(storage))
}
