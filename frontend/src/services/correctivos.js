import axios from 'axios'
import { API_URL } from '../config.js'
import { findEquipoByPatente } from './criticalScreens.js'

export const createTrabajoVacio = () => ({
  tipo_tarea_id: '',
  detalle: '',
  repuesto_id: '',
  cantidad: 0,
  precio_unitario: 0,
  mecanico_id: '',
  sector_id: '',
  observaciones: '',
})

export const fetchCorrectivosCatalogos = async () => {
  const response = await axios.get(`${API_URL}/correctivos/catalogos`)
  return response.data
}

export const registrarCorrectivo = async (payload) => {
  const response = await axios.post(`${API_URL}/correctivos`, payload)
  return response.data
}

export const resolveDefaultCorrectivoEquipo = (equipos, patente) => {
  if (!patente) return null
  return findEquipoByPatente(equipos || [], patente)
}

const cleanOptionalId = (value) => {
  if (value === '' || value === null || value === undefined) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

export const buildCorrectivoPayload = ({ form, trabajos }) => ({
  fecha: form.fecha,
  equipo_id: Number(form.equipo_id),
  km_hora: Number(form.km_hora || 0),
  descripcion: String(form.descripcion || '').trim(),
  externo: Boolean(form.externo),
  proveedor_id: form.externo ? cleanOptionalId(form.proveedor_id) : null,
  mecanico_id: cleanOptionalId(form.mecanico_id),
  unidad_negocio_id: Number(form.unidad_negocio_id),
  moneda_id: Number(form.moneda_id),
  cambio: Number(form.cambio || 1),
  orden_servicio: String(form.orden_servicio || '').trim(),
  trabajos: (trabajos || []).map((trabajo) => ({
    tipo_tarea_id: Number(trabajo.tipo_tarea_id),
    detalle: String(trabajo.detalle || '').trim(),
    repuesto_id: cleanOptionalId(trabajo.repuesto_id),
    cantidad: Number(trabajo.cantidad || 0),
    precio_unitario: Number(trabajo.precio_unitario || 0),
    mecanico_id: cleanOptionalId(trabajo.mecanico_id),
    sector_id: cleanOptionalId(trabajo.sector_id),
    observaciones: String(trabajo.observaciones || '').trim(),
  })),
})

export const validateCorrectivoForm = ({ form, trabajos }) => {
  const faltantes = []
  if (!form.fecha) faltantes.push('Fecha')
  if (!form.equipo_id) faltantes.push('Camión')
  if (form.km_hora === '' || form.km_hora === null || Number(form.km_hora) < 0) faltantes.push('KM/Hora')
  if (!String(form.descripcion || '').trim()) faltantes.push('Problema o incidencia')
  if (!form.unidad_negocio_id) faltantes.push('Unidad de negocio')
  if (!form.moneda_id) faltantes.push('Moneda')
  if (form.externo && !form.proveedor_id) faltantes.push('Proveedor')
  if (!Array.isArray(trabajos) || trabajos.length === 0) faltantes.push('Trabajo realizado')

  ;(trabajos || []).forEach((trabajo, index) => {
    if (!trabajo.tipo_tarea_id) faltantes.push(`Tarea #${index + 1}`)
    if (!String(trabajo.detalle || '').trim()) faltantes.push(`Detalle del trabajo #${index + 1}`)
  })

  return [...new Set(faltantes)]
}

export const formatCorrectivoApiError = (error) => {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length) {
    return detail.map((item) => item?.msg || String(item)).join('\n')
  }
  if (!error?.response) return 'No se pudo conectar con el servidor.'
  return `No se pudo registrar el correctivo (HTTP ${error.response.status}).`
}
