// @vitest-environment jsdom
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  catalog: {
    empleados: [{ id: 1, nombre: 'Chofer', apellido: 'Test', activo: true }],
    clientes: [],
    proveedores: [
      { id: 29, razon_social: 'INTERNO FORESTAL PARAGUAY', activo: true },
    ],
    equipos: [{ id: 4, patente: 'AAXO300', descripcion: 'Scania', activo: true }],
    unidadesNegocio: [{ id: 1, descripcion: 'Forestal', prefijo: 'F', activo: true }],
    panioles: [{ id: 1, descripcion: 'Tanque 1', activo: true }],
    tiposCombustible: [{ id: 1, descripcion: 'Diesel' }],
    isOffline: false,
    fetchCatalogues: vi.fn(async () => ({})),
  },
  push: vi.fn(),
  routeQuery: {},
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.push, replace: vi.fn() }),
  useRoute: () => ({ query: mocks.routeQuery }),
}))
vi.mock('../src/stores/catalog', () => ({ useCatalogStore: () => mocks.catalog }))
vi.mock('../src/services/fuelImage.js', async () => {
  const actual = await vi.importActual('../src/services/fuelImage.js')
  return {
    ...actual,
    analyzeFuelImage: vi.fn(async () => ({ upload_token: 'tok', tipo: 'ticket', proposal: {} })),
    confirmFuelTicketImage: vi.fn(async () => ({ movimiento_id: 10, imagen_id: 100 })),
    confirmFuelRemitoInternoImage: vi.fn(async () => ({ movimiento_id: 11, imagen_id: 101 })),
    prepareFuelImageForUpload: async (f) => f,
    fetchFuelImageBlob: vi.fn(async () => new Blob(['x'], { type: 'image/jpeg' })),
    createFuelImageObjectUrl: () => 'blob:preview',
    revokeFuelImageObjectUrl: () => {},
    mapFuelImageError: () => ({ message: 'mock error', action: 'review', retry: false }),
  }
})

import FuelImageUpload from '../src/views/FuelImageUpload.vue'

const buildRouter = (query = {}) => {
  const { createRouter, createMemoryHistory } = require('vue-router')
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/fuel-load', component: { template: '<div>back</div>' } },
      { path: '/settings', component: { template: '<div>settings</div>' } },
      { path: '/fuel-load/image', component: FuelImageUpload },
    ],
  })
}

const setLocalStorage = () => {
  localStorage.clear()
  localStorage.setItem('user', JSON.stringify({ id: 1 }))
  localStorage.setItem('default_patente', 'AAXO300')
  localStorage.setItem('default_unidad_negocio', '1')
}

describe('FuelImageUpload', () => {
  beforeEach(() => {
    setLocalStorage()
  })

  it('muestra el titulo de ticket de estacion cuando tipo=ticket', async () => {
    mocks.routeQuery = { tipo: 'ticket' }
    const router = buildRouter()
    await router.push('/fuel-load/image?tipo=ticket')
    await router.isReady()
    const wrapper = mount(FuelImageUpload, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('Cargar ticket de estación')
  })

  it('muestra el titulo de remito interno cuando tipo=remito_interno', async () => {
    mocks.routeQuery = { tipo: 'remito_interno' }
    const router = buildRouter()
    await router.push('/fuel-load/image?tipo=remito_interno')
    await router.isReady()
    const wrapper = mount(FuelImageUpload, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('Cargar remito interno')
  })

  it('cae a titulo generico cuando tipo no es valido', async () => {
    mocks.routeQuery = { tipo: 'otro' }
    const router = buildRouter()
    await router.push('/fuel-load/image?tipo=otro')
    await router.isReady()
    const wrapper = mount(FuelImageUpload, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('Cargar combustible desde foto')
  })

  it('los botones de volver a Combustible apuntan a /fuel-load', async () => {
    mocks.routeQuery = { tipo: 'ticket' }
    const router = buildRouter()
    await router.push('/fuel-load/image?tipo=ticket')
    await router.isReady()
    const wrapper = mount(FuelImageUpload, { global: { plugins: [router] } })
    await flushPromises()
    const backBtn = wrapper.find('button[aria-label="Volver a Combustible"]')
    expect(backBtn.exists()).toBe(true)
    await backBtn.trigger('click')
    expect(mocks.push).toHaveBeenCalledWith('/fuel-load')
  })
})
