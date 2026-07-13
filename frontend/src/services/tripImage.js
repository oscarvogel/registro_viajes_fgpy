import axios from 'axios'
import { API_URL } from '../config.js'

const endpoint = (apiUrl, path) => `${String(apiUrl).replace(/\/$/, '')}${path}`

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

const ERROR_BY_STATUS = {
  400: ['La solicitud de imagen no es válida.', false],
  401: ['Tu sesión venció. Iniciá sesión nuevamente.', false],
  403: ['No tenés permiso para cargar esta imagen.', false],
  409: ['Este comprobante ya fue confirmado.', false],
  410: ['La imagen venció. Volvé a analizarla.', true],
  413: ['La imagen es demasiado grande.', false],
  422: ['Revisá los datos detectados antes de confirmar.', false],
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
