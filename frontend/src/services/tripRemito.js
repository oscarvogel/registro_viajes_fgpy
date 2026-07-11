export const normalizeRemitoPart = (value, length) => {
  const digits = String(value || '').replace(/\D/g, '')
  return digits.padStart(length, '0').slice(-length)
}

export const combineRemito = (tipo, sucursal, numero) => {
  if (!tipo && !sucursal && !numero) return ''
  const t = normalizeRemitoPart(tipo, 3)
  const s = normalizeRemitoPart(sucursal, 3)
  const n = normalizeRemitoPart(numero, 7)
  return `${t}-${s}-${n}`
}
