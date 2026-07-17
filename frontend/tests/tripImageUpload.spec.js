// @vitest-environment jsdom
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  analyze: vi.fn(),
  confirm: vi.fn(),
  fetchBlob: vi.fn(),
  prepare: vi.fn(async (file) => file),
  createUrl: vi.fn(() => 'blob:preview'),
  revokeUrl: vi.fn(),
  catalog: {
    empleados: [{ id: 7, nombre: 'Ana', apellido: 'Pérez', activo: true }],
    clientes: [
      { id: 10, razon_social: 'Alcogreen', activo: true },
      { id: 11, razon_social: 'Cliente inactivo', activo: false },
    ],
    proveedores: [
      { id: 8, razon_social: 'Forestal Paraguay', activo: true },
      { id: 9, razon_social: 'Proveedor inactivo', activo: false },
    ],
    equipos: [{ id: 2, patente: 'AB 123 CD', descripcion: 'Camión', activo: true }],
    unidadesNegocio: [{ id: 4, descripcion: 'Forestal', prefijo: 'F', activo: true }],
    isOffline: false,
    fetchCatalogues: vi.fn(async () => ({})),
  },
  push: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push }) }))
vi.mock('../src/stores/catalog', () => ({ useCatalogStore: () => mocks.catalog }))
vi.mock('../src/services/tripImage.js', async () => {
  const actual = await vi.importActual('../src/services/tripImage.js')
  return {
    ...actual,
    analyzeTripImage: mocks.analyze,
    confirmTripImage: mocks.confirm,
    fetchTripImageBlob: mocks.fetchBlob,
    prepareTripImageForUpload: mocks.prepare,
    createTripImageObjectUrl: mocks.createUrl,
    revokeTripImageObjectUrl: mocks.revokeUrl,
  }
})

import TripImageUpload from '../src/views/TripImageUpload.vue'

const analysis = { upload_token: 'opaque', proposal: {
  fecha_remision: '2026-07-12', numero_remision_fpv: '001-002-0000003',
  cliente_id: 10, cliente_candidato: 'Alcogreen S.A.',
  proveedor_id: 8, proveedor_candidato: 'Forestal Paraguay S.A.',
  peso_bruto_destino: 49.69, tara_destino: 17.08, neto_destino: 32.61,
  warnings: [],
} }

const file = (name = 'ticket.jpg', type = 'image/jpeg') => {
  const value = new File(['image'], name, { type })
  return value
}

const selectFile = async (wrapper, value) => {
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [value] })
  await input.trigger('change')
  await flushPromises()
}

const mountView = async () => {
  const wrapper = mount(TripImageUpload)
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.catalog.isOffline = false
  localStorage.clear()
  localStorage.setItem('user', JSON.stringify({ id: 7 }))
  localStorage.setItem('default_patente', 'AB 123 CD')
  localStorage.setItem('default_unidad_negocio', '4')
  mocks.analyze.mockResolvedValue(analysis)
  mocks.confirm.mockResolvedValue({ viaje_id: 12, imagen_id: 21 })
  mocks.fetchBlob.mockResolvedValue(new Blob(['confirmed'], { type: 'image/jpeg' }))
  mocks.createUrl.mockReturnValueOnce('blob:local').mockReturnValue('blob:confirmed')
  mocks.prepare.mockImplementation(async (selected) => selected)
})

describe('TripImageUpload', () => {
  it('shows a safe error for an invalid file and never analyzes it', async () => {
    const wrapper = await mountView()
    await selectFile(wrapper, file('malware.gif', 'image/gif'))

    expect(wrapper.text()).toContain('El archivo debe ser una imagen JPG, PNG o WEBP.')
    expect(mocks.analyze).not.toHaveBeenCalled()
    expect(mocks.createUrl).not.toHaveBeenCalled()
  })

  it('moves to review after analysis and keeps the local preview when analysis fails', async () => {
    const success = await mountView()
    await selectFile(success, file())
    expect(mocks.analyze).toHaveBeenCalledTimes(1)
    expect(success.text()).toContain('Revisá los datos detectados')
    expect(success.get('img[alt="Foto original para revisar"]').attributes('src')).toBe('blob:local')
    success.unmount()

    mocks.analyze.mockRejectedValueOnce(new Error('network secret'))
    const failure = await mountView()
    await selectFile(failure, file())
    expect(failure.text()).toContain('No hay conexión. Verificá Internet e intentá nuevamente.')
    expect(failure.get('img[alt="Foto conservada para reintentar"]').attributes('src')).toBe('blob:local')
  })

  it('analyzes the prepared upload image while keeping the original preview', async () => {
    const original = file('remito-grande.png', 'image/png')
    const prepared = new File(['small'], 'remito-grande.jpg', { type: 'image/jpeg' })
    mocks.prepare.mockResolvedValueOnce(prepared)

    const wrapper = await mountView()
    await selectFile(wrapper, original)

    expect(mocks.prepare).toHaveBeenCalledWith(original)
    expect(mocks.createUrl).toHaveBeenCalledWith(original)
    expect(mocks.analyze).toHaveBeenCalledWith(prepared)
  })

  it('does not render an OCR warning block when configuration matches', async () => {
    const wrapper = await mountView()
    await selectFile(wrapper, file())

    expect(wrapper.text()).not.toContain('Datos observados en la foto')
    expect(wrapper.text()).not.toContain('Revisá la configuración')
  })

  it('renders active client and provider selectors with OCR proposals selected', async () => {
    const wrapper = await mountView()
    await selectFile(wrapper, file())

    const client = wrapper.get('select[aria-label="Cliente"]')
    const provider = wrapper.get('select[aria-label="Proveedor"]')
    expect(client.element.value).toBe('10')
    expect(provider.element.value).toBe('8')
    expect(client.text()).toContain('Alcogreen')
    expect(client.text()).not.toContain('Cliente inactivo')
    expect(provider.text()).toContain('Forestal Paraguay')
    expect(provider.text()).not.toContain('Proveedor inactivo')
  })

  it.each([
    ['cliente', { cliente_id: null }, 'Seleccioná un cliente activo válido.'],
    ['proveedor', { proveedor_id: null }, 'Seleccioná un proveedor activo válido.'],
  ])('does not confirm without %s', async (_label, proposalChange, message) => {
    mocks.analyze.mockResolvedValueOnce({
      ...analysis,
      proposal: { ...analysis.proposal, ...proposalChange },
    })
    const wrapper = await mountView()
    await selectFile(wrapper, file())
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mocks.confirm).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain(message)
  })

  it('renders one compact alert only for concrete configuration mismatches', async () => {
    mocks.analyze.mockResolvedValueOnce({
      ...analysis,
      proposal: {
        ...analysis.proposal,
        warnings: ['Texto general que no debe mostrarse'],
        patente_observada: 'ZZ999ZZ',
        chofer_observado: 'Otra Persona',
      },
    })
    const wrapper = await mountView()
    await selectFile(wrapper, file())

    const alert = wrapper.get('[role="alert"]')
    expect(alert.text()).toContain('Revisá la configuración')
    expect(alert.text()).toContain('La foto parece indicar ZZ999ZZ; en Ajustes figura AB 123 CD.')
    expect(alert.text()).toContain('La foto parece indicar Otra Persona; el usuario actual es Pérez Ana.')
    expect(alert.text()).not.toContain('Texto general que no debe mostrarse')
    expect(wrapper.text()).not.toContain('Datos observados en la foto')
  })

  it('preserves edited fields after confirmation error and retry', async () => {
    mocks.confirm.mockRejectedValueOnce({ response: { status: 503, data: { detail: 'secret' } } })
    const wrapper = await mountView()
    await selectFile(wrapper, file())
    const observations = wrapper.get('textarea')
    await observations.setValue('editado por operador')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('El servicio de lectura no está disponible.')
    const retry = wrapper.findAll('button').find((button) => button.text() === 'Reintentar')
    expect(retry).toBeTruthy()
    await retry.trigger('click')
    expect(wrapper.get('textarea').element.value).toBe('editado por operador')
    expect(wrapper.get('select[aria-label="Cliente"]').element.value).toBe('10')
    expect(wrapper.get('select[aria-label="Proveedor"]').element.value).toBe('8')
  })

  it('does not create or replace a confirmed preview after unmount', async () => {
    let resolveFetch
    mocks.fetchBlob.mockReturnValueOnce(new Promise((resolve) => { resolveFetch = resolve }))
    const wrapper = await mountView()
    await selectFile(wrapper, file())
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(mocks.createUrl).toHaveBeenCalledTimes(1)

    wrapper.unmount()
    resolveFetch(new Blob(['confirmed'], { type: 'image/jpeg' }))
    await flushPromises()

    expect(mocks.createUrl).toHaveBeenCalledTimes(1)
    expect(mocks.revokeUrl).toHaveBeenCalledWith('blob:local')
  })
})
