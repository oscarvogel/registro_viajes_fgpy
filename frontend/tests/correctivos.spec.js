// @vitest-environment jsdom
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  registrar: vi.fn(async () => ({ id: 55, estado: 'Cerrado', trabajos: 1 })),
  catalogos: {
    tareas: [{ id: 3, descripcion: 'Gomeria' }, { id: 4, descripcion: 'Mecanica' }],
    repuestos: [{ id: 30, descripcion: 'Valvula' }],
    monedas: [{ id: 1, descripcion: 'Guaranies', simbolo: 'Gs', cambio: 1 }],
    sectores: [{ id: 2, descripcion: 'Taller' }],
    proveedores: [{ id: 20, descripcion: 'Gomeria Test' }],
    mecanicos: [{ id: 8, descripcion: 'Mecanico Juan' }],
    equipos: [{ id: 10, patente: 'AA PL 657', descripcion: 'Camion KIA', tipo_movil_id: 4, ult_hr_km: 185000 }],
    unidades_negocio: [{ id: 1, descripcion: 'Transporte' }],
  },
}))

vi.mock('../src/services/correctivos.js', async () => {
  const actual = await vi.importActual('../src/services/correctivos.js')
  return {
    ...actual,
    fetchCorrectivosCatalogos: vi.fn(async () => mocks.catalogos),
    registrarCorrectivo: mocks.registrar,
  }
})

import CorrectiveCreate from '../src/views/CorrectiveCreate.vue'

const mountView = async () => {
  const wrapper = mount(CorrectiveCreate, {
    global: {
      stubs: {
        Autocomplete: {
          props: ['modelValue', 'items', 'label'],
          emits: ['update:modelValue'],
          template: '<div data-test="autocomplete">{{ label }}: {{ modelValue }}</div>',
        },
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('CorrectiveCreate', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('default_patente', 'aapl657')
    localStorage.setItem('default_unidad_negocio', '1')
    mocks.registrar.mockClear()
  })

  it('reutiliza camion configurado y ultimo km/hora', async () => {
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('Registrar correctivo')
    expect(wrapper.find('[data-test="autocomplete"]').text()).toContain('10')
    const kmInput = wrapper.find('input[type="number"]')
    expect(Number(kmInput.element.value)).toBe(185000)
  })

  it('muestra proveedor al marcar atención externa', async () => {
    const wrapper = await mountView()
    expect(wrapper.text()).not.toContain('Seleccione proveedor')
    const externo = wrapper.find('input[type="checkbox"]')
    await externo.setValue(true)
    expect(wrapper.text()).toContain('Seleccione proveedor')
  })

  it('permite agregar y quitar trabajos', async () => {
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('Trabajo 1')
    const add = wrapper.findAll('button').find((button) => button.text().includes('+ Agregar'))
    await add.trigger('click')
    expect(wrapper.text()).toContain('Trabajo 2')
    const remove = wrapper.findAll('button').find((button) => button.text() === 'Quitar')
    await remove.trigger('click')
    expect(wrapper.text()).not.toContain('Trabajo 2')
  })
})
