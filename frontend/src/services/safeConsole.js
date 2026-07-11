const callConsole = (method, args) => {
  try {
    globalThis.console?.[method]?.(...args)
  } catch (e) {
    // Logging should never interrupt the operator workflow.
  }
}

export const safeConsole = {
  debug: (...args) => callConsole('debug', args),
  error: (...args) => callConsole('error', args),
  info: (...args) => callConsole('info', args),
  log: (...args) => callConsole('log', args),
  warn: (...args) => callConsole('warn', args),
}

export default safeConsole
