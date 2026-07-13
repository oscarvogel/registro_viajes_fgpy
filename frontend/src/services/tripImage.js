import axios from 'axios'
import { API_URL } from '../config.js'

const endpoint = (apiUrl, path) => `${String(apiUrl).replace(/\/$/, '')}${path}`

const TRIP_IMAGE_MAX_BYTES = 10 * 1024 * 1024
const TRIP_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])
const TRIP_IMAGE_EXTENSION = /\.(?:jpe?g|png|webp)$/i

export const validateTripImageFile = (file, maxBytes = TRIP_IMAGE_MAX_BYTES) => {
  if (typeof Blob === 'undefined' || !(file instanceof Blob)) throw new TypeError('Seleccioná una imagen válida.')
  const type = String(file.type || '').trim().toLowerCase()
  const name = typeof file.name === 'string' ? file.name.trim() : ''
  const supported = type ? TRIP_IMAGE_TYPES.has(type) : TRIP_IMAGE_EXTENSION.test(name)
  if (!supported) throw new TypeError('El archivo debe ser una imagen JPG, PNG o WEBP.')
  if (!Number.isFinite(maxBytes) || maxBytes <= 0 || file.size <= 0) throw new TypeError('La imagen está vacía o no es válida.')
  if (file.size > maxBytes) throw new TypeError('La imagen es demasiado grande. El máximo es 10 MB.')
  return file
}

export const createTripImageLifecycle = () => {
  let active = true
  return {
    get active() { return active },
    deactivate() { active = false },
    runIfActive(callback) { return active ? callback() : undefined },
  }
}

export const analyzeTripImage = async (file, httpClient = axios, apiUrl = API_URL) => {
  if (typeof Blob === 'undefined' || !(file instanceof Blob)) throw new TypeError('Seleccioná una imagen válida.')
  const body = new FormData()
  const filename = typeof file.name === 'string' && file.name.trim() ? file.name.trim() : 'image'
  body.append('file', file, filename)
  const response = await httpClient.post(endpoint(apiUrl, '/registro-viaje/imagen/analizar'), body)
  return response.data
}

export const confirmTripImage = async (payload, httpClient = axios, apiUrl = API_URL) => {
  const response = await httpClient.post(endpoint(apiUrl, '/registro-viaje/imagen/confirmar'), payload)
  return response.data
}

export const tripImageUrl = (id, apiUrl = API_URL) => {
  if (!Number.isInteger(id) || id <= 0) throw new TypeError('El id de imagen debe ser un entero positivo.')
  return endpoint(apiUrl, `/registro-viaje/imagenes/${encodeURIComponent(String(id))}`)
}

const isImageBlob = (value) => (
  typeof Blob !== 'undefined'
  && value instanceof Blob
  && /^image\/[a-z0-9.+-]+$/i.test(value.type)
)

export const fetchTripImageBlob = async (id, httpClient = axios, apiUrl = API_URL) => {
  const response = await httpClient.get(tripImageUrl(id, apiUrl), { responseType: 'blob' })
  if (!isImageBlob(response?.data)) throw new TypeError('La respuesta no contiene una imagen válida.')
  return response.data
}

export const createTripImageObjectUrl = (blob, urlApi = URL) => {
  if (!isImageBlob(blob) || typeof urlApi?.createObjectURL !== 'function') throw new TypeError('No se puede mostrar una imagen inválida.')
  return urlApi.createObjectURL(blob)
}

export const revokeTripImageObjectUrl = (url, urlApi = URL) => {
  if (typeof url === 'string' && url && typeof urlApi?.revokeObjectURL === 'function') urlApi.revokeObjectURL(url)
}

const ERROR_BY_STATUS = {
  400: ['La solicitud de imagen no es válida.', false],
  401: ['Tu sesión venció. Iniciá sesión nuevamente.', false],
  403: ['No tenés permiso para cargar esta imagen.', false],
  409: ['Este comprobante ya fue confirmado.', false],
  410: ['La imagen venció. Volvé a analizarla.', true],
  413: ['La imagen es demasiado grande.', false],
  422: ['Revisá los datos detectados antes de confirmar.', false],
  404: ['No se encontró la imagen solicitada.', false],
  429: ['Hay demasiadas solicitudes. Esperá un momento e intentá nuevamente.', true],
  500: ['El servidor no pudo procesar la imagen.', true],
  502: ['El servicio de lectura no está disponible.', true],
  503: ['El servicio de lectura no está disponible.', true],
  504: ['El servicio tardó demasiado en responder.', true],
}

export const mapTripImageError = (error) => {
  const status = Number(error?.response?.status)
  const [message, retry] = ERROR_BY_STATUS[status]
    || ['No hay conexión. Verificá Internet e intentá nuevamente.', true]
  return { message, action: retry ? 'retry' : 'review', retry }
}
