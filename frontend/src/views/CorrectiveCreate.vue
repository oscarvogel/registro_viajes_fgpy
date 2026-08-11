<script setup>
import { computed, onMounted, ref } from 'vue'
import Swal from 'sweetalert2'
import Autocomplete from '../components/Autocomplete.vue'
import {
  buildCorrectivoPayload,
  createTrabajoVacio,
  fetchCorrectivosCatalogos,
  formatCorrectivoApiError,
  registrarCorrectivo,
  resolveDefaultCorrectivoEquipo,
  validateCorrectivoForm,
} from '../services/correctivos'

const loading = ref(true)
const saving = ref(false)
const catalogos = ref({
  tareas: [],
  repuestos: [],
  monedas: [],
  sectores: [],
  proveedores: [],
  mecanicos: [],
  equipos: [],
  unidades_negocio: [],
})

const form = ref({
  fecha: new Date().toISOString().split('T')[0],
  equipo_id: '',
  km_hora: '',
  descripcion: '',
  externo: false,
  proveedor_id: '',
  mecanico_id: '',
  unidad_negocio_id: '',
  moneda_id: '',
  cambio: 1,
  orden_servicio: '',
})

const trabajos = ref([createTrabajoVacio()])

const equipoSeleccionado = computed(() =>
  catalogos.value.equipos.find((item) => Number(item.id) === Number(form.value.equipo_id)) || null
)

const monedaSeleccionada = computed(() =>
  catalogos.value.monedas.find((item) => Number(item.id) === Number(form.value.moneda_id)) || null
)

const agregarTrabajo = () => trabajos.value.push(createTrabajoVacio())

const quitarTrabajo = (index) => {
  if (trabajos.value.length <= 1) return
  trabajos.value.splice(index, 1)
}

const aplicarDefaults = () => {
  const defaultPatente = localStorage.getItem('default_patente')
  const equipo = resolveDefaultCorrectivoEquipo(catalogos.value.equipos, defaultPatente)
  if (equipo) {
    form.value.equipo_id = equipo.id
    form.value.km_hora = Number(equipo.ult_hr_km || 0)
  }

  const unidadGuardada = Number(localStorage.getItem('default_unidad_negocio') || 0)
  if (unidadGuardada && catalogos.value.unidades_negocio.some((item) => Number(item.id) === unidadGuardada)) {
    form.value.unidad_negocio_id = unidadGuardada
  } else if (catalogos.value.unidades_negocio.length === 1) {
    form.value.unidad_negocio_id = catalogos.value.unidades_negocio[0].id
  }

  if (catalogos.value.monedas.length) {
    form.value.moneda_id = catalogos.value.monedas[0].id
    form.value.cambio = Number(catalogos.value.monedas[0].cambio || 1)
  }
}

const onMonedaChange = () => {
  if (monedaSeleccionada.value) {
    form.value.cambio = Number(monedaSeleccionada.value.cambio || 1)
  }
}

const onEquipoChange = () => {
  if (equipoSeleccionado.value && (form.value.km_hora === '' || Number(form.value.km_hora) === 0)) {
    form.value.km_hora = Number(equipoSeleccionado.value.ult_hr_km || 0)
  }
}

const cargarCatalogos = async () => {
  loading.value = true
  try {
    catalogos.value = await fetchCorrectivosCatalogos()
    aplicarDefaults()
  } catch (error) {
    await Swal.fire({
      icon: 'error',
      title: 'No se pudieron cargar los catálogos',
      text: formatCorrectivoApiError(error),
      confirmButtonColor: '#2563eb',
    })
  } finally {
    loading.value = false
  }
}

const resetAfterSave = () => {
  const equipoId = form.value.equipo_id
  const kmHora = form.value.km_hora
  const unidadId = form.value.unidad_negocio_id
  const monedaId = form.value.moneda_id
  const cambio = form.value.cambio

  form.value = {
    fecha: new Date().toISOString().split('T')[0],
    equipo_id: equipoId,
    km_hora: kmHora,
    descripcion: '',
    externo: false,
    proveedor_id: '',
    mecanico_id: '',
    unidad_negocio_id: unidadId,
    moneda_id: monedaId,
    cambio,
    orden_servicio: '',
  }
  trabajos.value = [createTrabajoVacio()]
}

const submitForm = async () => {
  const faltantes = validateCorrectivoForm({ form: form.value, trabajos: trabajos.value })
  if (faltantes.length) {
    await Swal.fire({
      icon: 'warning',
      title: 'Faltan datos obligatorios',
      html: `<div style="text-align:left"><ul>${faltantes.map((item) => `<li>${item}</li>`).join('')}</ul></div>`,
      confirmButtonColor: '#2563eb',
    })
    return
  }

  saving.value = true
  try {
    const result = await registrarCorrectivo(buildCorrectivoPayload({ form: form.value, trabajos: trabajos.value }))
    await Swal.fire({
      icon: 'success',
      title: 'Correctivo registrado',
      text: `Intervención #${result.id} guardada con ${result.trabajos} trabajo${result.trabajos === 1 ? '' : 's'}.`,
      timer: 1800,
      showConfirmButton: false,
    })
    resetAfterSave()
  } catch (error) {
    await Swal.fire({
      icon: 'error',
      title: 'No se pudo registrar',
      text: formatCorrectivoApiError(error),
      confirmButtonColor: '#2563eb',
    })
  } finally {
    saving.value = false
  }
}

onMounted(cargarCatalogos)
</script>

<template>
  <section class="mx-auto max-w-3xl px-4 py-5 pb-24">
    <div class="mb-5 rounded-xl border border-rose-100 bg-rose-50 p-4 dark:border-rose-900/60 dark:bg-rose-950/30">
      <p class="text-xs font-semibold uppercase tracking-wide text-rose-700 dark:text-rose-300">Mantenimiento</p>
      <h2 class="mt-1 text-xl font-bold text-gray-900 dark:text-white">Registrar correctivo</h2>
      <p class="mt-1 text-sm text-gray-600 dark:text-gray-300">Registra una incidencia y todo el trabajo realizado sobre el camión o equipo.</p>
    </div>

    <div v-if="loading" class="rounded-xl border bg-white p-6 text-center text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-800">
      Cargando catálogos…
    </div>

    <form v-else class="space-y-5" @submit.prevent="submitForm">
      <section class="rounded-xl border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 class="mb-4 font-semibold">Incidencia</h3>
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-500">Fecha</label>
            <input v-model="form.fecha" type="date" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900" />
          </div>
          <div>
            <Autocomplete
              label="Camión / equipo"
              :items="catalogos.equipos"
              v-model="form.equipo_id"
              :displayFn="(e) => `${e.patente} • ${e.descripcion}`"
              placeholder="Seleccione un equipo"
              @update:modelValue="onEquipoChange"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-500">KM / Hora</label>
            <input v-model.number="form.km_hora" type="number" min="0" step="0.01" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900" />
            <p v-if="equipoSeleccionado" class="mt-1 text-xs text-gray-500">Último valor del equipo: {{ Number(equipoSeleccionado.ult_hr_km || 0).toLocaleString() }}</p>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-500">Unidad de negocio</label>
            <select v-model="form.unidad_negocio_id" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900">
              <option value="" disabled>Seleccione</option>
              <option v-for="item in catalogos.unidades_negocio" :key="item.id" :value="item.id">{{ item.descripcion }}</option>
            </select>
          </div>
        </div>
        <div class="mt-4">
          <label class="mb-1 block text-xs font-medium text-gray-500">Problema / incidencia</label>
          <textarea v-model="form.descripcion" rows="3" maxlength="4000" placeholder="Ej.: pinchadura cubierta trasera derecha" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900"></textarea>
        </div>
      </section>

      <section class="rounded-xl border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h3 class="font-semibold">Tipo de atención</h3>
            <p class="text-xs text-gray-500">Interna o realizada por un proveedor externo.</p>
          </div>
          <label class="inline-flex items-center gap-2 rounded-full border px-3 py-2 text-sm dark:border-gray-600">
            <input v-model="form.externo" type="checkbox" class="h-4 w-4" />
            Externo
          </label>
        </div>

        <div class="mt-4 grid gap-4 sm:grid-cols-2">
          <div v-if="form.externo">
            <label class="mb-1 block text-xs font-medium text-gray-500">Proveedor</label>
            <select v-model="form.proveedor_id" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900">
              <option value="" disabled>Seleccione proveedor</option>
              <option v-for="item in catalogos.proveedores" :key="item.id" :value="item.id">{{ item.descripcion }}</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-500">Mecánico responsable</label>
            <select v-model="form.mecanico_id" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900">
              <option value="">Sin asignar</option>
              <option v-for="item in catalogos.mecanicos" :key="item.id" :value="item.id">{{ item.descripcion }}</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-500">Referencia proveedor / OS</label>
            <input v-model="form.orden_servicio" maxlength="12" type="text" placeholder="Opcional" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900" />
          </div>
        </div>
      </section>

      <section class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="font-semibold">Trabajos realizados</h3>
            <p class="text-xs text-gray-500">Una incidencia puede tener varios trabajos.</p>
          </div>
          <button type="button" @click="agregarTrabajo" class="rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white dark:bg-gray-100 dark:text-gray-900">+ Agregar</button>
        </div>

        <article v-for="(trabajo, index) in trabajos" :key="index" class="rounded-xl border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <div class="mb-3 flex items-center justify-between">
            <h4 class="font-medium">Trabajo {{ index + 1 }}</h4>
            <button v-if="trabajos.length > 1" type="button" @click="quitarTrabajo(index)" class="text-sm font-medium text-red-600">Quitar</button>
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div>
              <label class="mb-1 block text-xs font-medium text-gray-500">Tarea / tipo</label>
              <select v-model="trabajo.tipo_tarea_id" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900">
                <option value="" disabled>Seleccione tarea</option>
                <option v-for="item in catalogos.tareas" :key="item.id" :value="item.id">{{ item.descripcion }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium text-gray-500">Sector</label>
              <select v-model="trabajo.sector_id" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900">
                <option value="">Sin sector</option>
                <option v-for="item in catalogos.sectores" :key="item.id" :value="item.id">{{ item.descripcion }}</option>
              </select>
            </div>
          </div>
          <div class="mt-4">
            <label class="mb-1 block text-xs font-medium text-gray-500">Trabajo realizado</label>
            <textarea v-model="trabajo.detalle" rows="3" placeholder="Ej.: desarme, reparación y montaje" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900"></textarea>
          </div>
          <details class="mt-4 rounded-lg border p-3 dark:border-gray-700">
            <summary class="cursor-pointer text-sm font-medium">Repuestos, costos y observaciones (opcional)</summary>
            <div class="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <label class="mb-1 block text-xs font-medium text-gray-500">Repuesto</label>
                <select v-model="trabajo.repuesto_id" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900">
                  <option value="">Sin repuesto</option>
                  <option v-for="item in catalogos.repuestos" :key="item.id" :value="item.id">{{ item.descripcion }}</option>
                </select>
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium text-gray-500">Cantidad</label>
                <input v-model.number="trabajo.cantidad" type="number" min="0" step="0.01" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900" />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium text-gray-500">Precio unitario</label>
                <input v-model.number="trabajo.precio_unitario" type="number" min="0" step="0.01" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900" />
              </div>
              <div>
                <label class="mb-1 block text-xs font-medium text-gray-500">Mecánico de este trabajo</label>
                <select v-model="trabajo.mecanico_id" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900">
                  <option value="">Usar responsable general</option>
                  <option v-for="item in catalogos.mecanicos" :key="item.id" :value="item.id">{{ item.descripcion }}</option>
                </select>
              </div>
            </div>
            <div class="mt-4">
              <label class="mb-1 block text-xs font-medium text-gray-500">Observaciones</label>
              <textarea v-model="trabajo.observaciones" rows="2" maxlength="200" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900"></textarea>
            </div>
          </details>
        </article>
      </section>

      <section class="rounded-xl border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <h3 class="mb-4 font-semibold">Moneda</h3>
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-500">Moneda</label>
            <select v-model="form.moneda_id" @change="onMonedaChange" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900">
              <option value="" disabled>Seleccione</option>
              <option v-for="item in catalogos.monedas" :key="item.id" :value="item.id">{{ item.descripcion }} {{ item.simbolo ? `(${item.simbolo})` : '' }}</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-gray-500">Cambio</label>
            <input v-model.number="form.cambio" type="number" min="0.0001" step="0.0001" class="w-full rounded-lg border p-3 dark:border-gray-700 dark:bg-gray-900" />
          </div>
        </div>
      </section>

      <button type="submit" :disabled="saving" class="min-h-12 w-full rounded-xl bg-rose-600 px-4 py-3 font-semibold text-white shadow-lg disabled:opacity-60">
        {{ saving ? 'Guardando…' : 'Registrar correctivo' }}
      </button>
    </form>
  </section>
</template>
