export const LOGIN_FALLBACK_ERROR = 'Error de ingreso. Verifique DNI.'

export const getLoginErrorMessage = (error) => {
  return error?.response?.data?.detail || error?.message || LOGIN_FALLBACK_ERROR
}

export const storeLoginSession = (loginData, storage = globalThis.localStorage) => {
  storage.setItem('token', loginData.access_token)
  storage.setItem('user', JSON.stringify(loginData.user))
}

export const DEFAULT_LOGIN_REDIRECT = '/new-trip'

export const resolveLoginRedirect = (redirectTo, fallback = DEFAULT_LOGIN_REDIRECT) => {
  if (typeof redirectTo !== 'string') return fallback

  const trimmed = redirectTo.trim()
  if (!trimmed || !trimmed.startsWith('/') || trimmed.startsWith('//')) return fallback
  if (trimmed.startsWith('/login')) return fallback

  return trimmed
}

export const loginAndNavigate = async ({
  dni,
  apiUrl,
  httpClient,
  storage = globalThis.localStorage,
  router,
  clientLogger,
  afterLogin,
  redirectTo,
}) => {
  try {
    const response = await httpClient.post(`${apiUrl}/login`, {
      documento: dni,
    })

    storeLoginSession(response.data, storage)

    try {
      clientLogger?.setUserId(response.data.user.id)
    } catch (e) {
      // Login must not fail because telemetry setup failed.
    }

    try {
      await afterLogin?.(response.data)
    } catch (e) {
      // Version checks and update prompts are non-blocking after login.
    }

    await router.push(resolveLoginRedirect(redirectTo))

    return { ok: true, data: response.data }
  } catch (error) {
    return { ok: false, error: getLoginErrorMessage(error) }
  }
}
