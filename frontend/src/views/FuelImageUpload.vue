<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCatalogStore } from '../stores/catalog'
import {
  FUEL_TIPO_REMITO_INTERNO,
  FUEL_TIPO_TICKET,
  analyzeFuelImage,
  confirmFuelRemitoInternoImage,
  confirmFuelTicketImage,
  createFuelImageLifecycle,
  createFuelImageObjectUrl,
  fetchFuelImageBlob,
  mapFuelImageError,
  prepareFuelImageForUpload,
  revokeFuelImageObjectUrl,
  validateFuelImageFile,
} from '../services/fuelImage.js'
import {
  buildConfirmPayload,
  createReviewModel,
  readFuelImageSettings,
  transitionReviewState,
} from '../services/fuelImageReview.js'

const route = useRoute()
const router = useRouter()
const catalog = useCatalogStore()

const state = ref('selecting')
const selectedFile = ref(null)
const previewUrl = ref('')
const review = ref(null)
const settings = ref(null)
const result = ref(null)
const errorMessage = ref('')
const errorAction = ref('reset')
const failedStep = ref('')
const fileInput = ref(null)
const lifecycle = createFuelImageLifecycle()

const tipo = computed(() => {
  const raw = String(route.query.tipo || '').trim()
  if (raw === FUEL_TIPO_TICKET) return FUEL_TIPO_TICKET
  if (raw === FUEL_TIPO_REMITO_INTERNO) return FUEL_TIPO_REMITO_INTERNO
  return null
})

const isTicket = computed(() => tipo.value === FUEL_TIPO_TICKET)
const isRemito = computed(() => tipo.value === FUEL_TIPO_REMITO_INTERNO)

const activeProviders = computed(() =>
  catalog.proveedores.filter((item) => item.activo === true)
)
const activeTanques = computed(() =>
  (catalog.panioles || []).filter((item) => item.activo === true)
)
const activeTiposCombustible = computed(() =>
  (catalog.tiposCombustible || catalog.tipos_combustible || []).filter(
    (item) => item.activo === true || item.activo === undefined
  )
)

const busy = computed(() => state.value === 'processing' || state.value === 'confirming')
const offline = computed(() => catalog.isOffline || (typeof navigator !== 'undefined' && navigator.onLine === false))
const configurationMissing = computed(() => !settings.value?.complete)
const internoMissing = computed(() => isRemito.value && !settings.value?.internoId)
const configuredDriver = computed(() => {
  const user = settings.value?.user
  return user ? `${user.apellido} ${user.nombre}`.trim() : 'Sin configurar'
})
const pageTitle = computed(() => {
  if (isTicket.value) return 'Cargar ticket de estación'
  if (isRemito.value) return 'Cargar remito interno'
  return 'Cargar combustible desde foto'
})
const badgeLabel = computed(() => {
  if (isTicket.value) return 'Ticket de estación (INFONET)'
  if (isRemito.value) return 'Remito interno (Forestal Paraguay)'
  return ''
})

const localToday = () => {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const replacePreview = (blob) => {
  const next = createFuelImageObjectUrl(blob)
  if (previewUrl.value) revokeFuelImageObjectUrl(previewUrl.value)
  previewUrl.value = next
}

const refreshSettings = () => {
  settings.value = readFuelImageSettings({ storage: localStorage, catalog })
}

const showError = (error, step) => {
  const mapped = error instanceof TypeError
    ? { message: error.message, action: 'review', retry: false }
    : mapFuelImageError(error)
  errorMessage.value = mapped.message
  errorAction.value = mapped.action
  failedStep.value = step
  state.value = 'error'
}

const analyzeSelected = async () => {
  if (busy.value || !selectedFile.value || !tipo.value) return
  refreshSettings()
  if (!settings.value.complete) {
    errorMessage.value = 'Completá Chofer, Patente y Unidad de Negocio en Ajustes antes de analizar.'
    errorAction.value = 'settings'
    failedStep.value = 'analyze'
    state.value = 'error'
    return
  }
  if (internoMissing.value) {
    errorMessage.value = 'Falta el proveedor INTERNO en el catálogo. Contactá a soporte.'
    errorAction.value = 'settings'
    failedStep.value = 'analyze'
    state.value = 'error'
    return
  }
  if (offline.value) {
    errorMessage.value = 'La carga desde foto necesita conexión a Internet.'
    errorAction.value = 'retry'
    failedStep.value = 'analyze'
    state.value = 'error'
    return
  }
  state.value = state.value === 'selecting'
    ? transitionReviewState('selecting', 'PROCESS')
    : 'processing'
  try {
    const analysis = await analyzeFuelImage(selectedFile.value, tipo.value)
    review.value = createReviewModel(analysis, settings.value, localToday(), tipo.value)
    state.value = transitionReviewState('processing', 'ANALYZED')
  } catch (error) {
    showError(error, 'analyze')
  }
}

const chooseFile = async (event) => {
  const file = event.target.files?.[0]
  if (!file) return
  let uploadFile
  try {
    validateFuelImageFile(file, Number.MAX_SAFE_INTEGER)
    uploadFile = await prepareFuelImageForUpload(file)
  } catch (error) {
    showError(error, 'select')
    return
  }
  replacePreview(file)
  selectedFile.value = uploadFile
  review.value = null
  result.value = null
  errorMessage.value = ''
  state.value = 'selecting'
  await analyzeSelected()
}

const confirmReview = async () => {
  if (busy.value || !review.value) return
  refreshSettings()
  if (!settings.value.complete) {
    errorMessage.value = 'La configuración cambió o está incompleta. Revisá Ajustes.'
    errorAction.value = 'settings'
    failedStep.value = 'confirm'
    state.value = 'error'
    return
  }
  if (internoMissing.value) {
    errorMessage.value = 'Falta el proveedor INTERNO en el catálogo. Contactá a soporte.'
    errorAction.value = 'settings'
    failedStep.value = 'confirm'
    state.value = 'error'
    return
  }
  if (offline.value) {
    errorMessage.value = 'Se perdió la conexión. Tus cambios siguen disponibles para reintentar.'
    errorAction.value = 'review'
    failedStep.value = 'confirm'
    state.value = 'error'
    return
  }
  let payload
  try {
    payload = buildConfirmPayload(review.value, settings.value, tipo.value)
  } catch (error) {
    showError(error, 'confirm')
    return
  }
  state.value = transitionReviewState('reviewing', 'CONFIRM')
  try {
    const confirmFn = isTicket.value
      ? confirmFuelTicketImage
      : confirmFuelRemitoInternoImage
    result.value = await confirmFn(payload)
    state.value = transitionReviewState('confirming', 'CONFIRMED')
    const imageId = Number(result.value?.imagen_id ?? result.value?.image_id)
    if (Number.isInteger(imageId) && imageId > 0) {
      try {
        const confirmedBlob = await fetchFuelImageBlob(imageId)
        lifecycle.runIfActive(() => replacePreview(confirmedBlob))
      } catch {
        // El registro ya quedó confirmado; se conserva la vista previa local.
      }
    }
  } catch (error) {
    showError(error, 'confirm')
  }
}

const returnToReview = () => {
  errorMessage.value = ''
  state.value = review.value ? 'reviewing' : 'selecting'
}

const retry = () => {
  errorMessage.value = ''
  if (failedStep.value === 'confirm') returnToReview()
  else analyzeSelected()
}

const reset = () => {
  if (previewUrl.value) revokeFuelImageObjectUrl(previewUrl.value)
  previewUrl.value = ''
  selectedFile.value = null
  review.value = null
  result.value = null
  errorMessage.value = ''
  errorAction.value = 'reset'
  state.value = 'selecting'
  if (fileInput.value) fileInput.value.value = ''
}

const cancelAndGoBack = () => {
  router.push('/fuel-load')
}

onMounted(async () => {
  if (!tipo.value) {
    router.replace('/fuel-load')
    return
  }
  await catalog.fetchCatalogues()
  refreshSettings()
})

onUnmounted(() => {
  lifecycle.deactivate()
  if (previewUrl.value) revokeFuelImageObjectUrl(previewUrl.value)
})
</script>

<template>
  <main class="mx-auto max-w-md overflow-x-hidden p-4 pb-24 text-gray-900 dark:text-gray-100">
    <header class="mb-6 flex items-center justify-between gap-3">
      <button type="button" class="min-h-11 rounded-lg px-3 text-blue-700 hover:bg-blue-50 dark:text-blue-300 dark:hover:bg-gray-800" aria-label="Volver a Combustible" @click="cancelAndGoBack">← Volver</button>
      <h1 class="min-w-0 flex-1 text-center text-lg font-bold">{{ pageTitle }}</h1>
      <span class="rounded-full px-2 py-1 text-xs font-medium" :class="offline ? 'bg-orange-100 text-orange-800' : 'bg-green-100 text-green-800'">{{ offline ? 'Sin conexión' : 'Conectado' }}</span>
    </header>

    <p class="sr-only" aria-live="polite">Estado: {{ state }}</p>

    <section v-if="state === 'selecting'" class="rounded-xl border border-amber-200 bg-white p-5 shadow-sm dark:border-amber-900 dark:bg-gray-800">
      <h2 class="text-lg font-semibold">Fotografiá el comprobante</h2>
      <p class="mt-2 text-sm text-gray-600 dark:text-gray-300">
        {{ isTicket ? 'Ticket impreso (INFONET, Petrobras, Lider Express). Asegurate que se vea el RUC y el remito.' : 'Remito manuscrito de Forestal Paraguay. Asegurate que se vea la firma y el número.' }}
      </p>
      <div v-if="configurationMissing" class="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
        Falta configurar Chofer, Patente o Unidad de Negocio.
        <button type="button" class="mt-2 block min-h-11 font-semibold underline" @click="router.push('/settings')">Ir a Ajustes</button>
      </div>
      <div v-if="internoMissing" class="mt-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200">
        Falta el proveedor INTERNO en el catálogo. Contactá a soporte antes de cargar remitos internos.
      </div>
      <div v-if="offline" class="mt-4 rounded-lg border border-orange-300 bg-orange-50 p-3 text-sm text-orange-900 dark:border-orange-800 dark:bg-orange-950/40 dark:text-orange-200">Esta función requiere conexión. Conectate para analizar una foto.</div>
      <input ref="fileInput" class="sr-only" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" aria-label="Elegir foto del comprobante" :disabled="offline || configurationMissing || internoMissing" @change="chooseFile">
      <button type="button" class="mt-5 min-h-14 w-full rounded-xl bg-amber-600 px-4 py-3 text-base font-semibold text-white shadow hover:bg-amber-700 disabled:cursor-not-allowed disabled:bg-gray-400" :disabled="offline || configurationMissing || internoMissing" @click="fileInput?.click()">📷 Tomar foto o elegir imagen</button>
    </section>

    <section v-else-if="state === 'processing'" class="space-y-4 text-center">
      <img v-if="previewUrl" :src="previewUrl" alt="Foto del comprobante" class="max-h-[55vh] w-full rounded-xl bg-gray-100 object-contain shadow dark:bg-gray-800">
      <div class="rounded-xl bg-white p-5 shadow dark:bg-gray-800" role="status">
        <span class="mx-auto block h-9 w-9 animate-spin rounded-full border-4 border-amber-200 border-t-amber-600"></span>
        <h2 class="mt-3 font-semibold">Analizando la imagen…</h2>
        <p class="mt-1 text-sm text-gray-500">Esto puede demorar unos segundos.</p>
      </div>
      <button type="button" class="min-h-11 w-full rounded-lg border border-gray-300 px-4" @click="cancelAndGoBack">Cancelar y volver</button>
    </section>

    <form v-else-if="state === 'reviewing' || state === 'confirming'" class="space-y-4" @submit.prevent="confirmReview">
      <img v-if="previewUrl" :src="previewUrl" alt="Foto original para revisar" class="max-h-[48vh] w-full rounded-xl bg-gray-100 object-contain shadow dark:bg-gray-800">

      <section v-if="badgeLabel" class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100" role="status">
        {{ badgeLabel }}
      </section>

      <section
        v-if="review?.configurationWarnings?.length"
        class="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100"
        role="alert"
      >
        <h2 class="font-semibold">Revisá la configuración</h2>
        <ul class="mt-2 list-disc space-y-1 pl-5">
          <li v-for="warning in review.configurationWarnings" :key="warning">{{ warning }}</li>
        </ul>
      </section>

      <section class="space-y-4 rounded-xl bg-white p-4 shadow dark:bg-gray-800">
        <h2 class="font-semibold">Revisá los datos detectados</h2>
        <div class="grid grid-cols-2 gap-3">
          <label class="text-xs font-medium text-gray-600 dark:text-gray-300">Fecha de carga<input v-model="review.fecha_carga" required type="date" class="mt-1 min-h-11 w-full rounded-lg border p-2 dark:border-gray-600 dark:bg-gray-700"></label>
          <label class="text-xs font-medium text-gray-600 dark:text-gray-300">Hora (opcional)<input v-model="review.hora_carga" type="time" class="mt-1 min-h-11 w-full rounded-lg border p-2 dark:border-gray-600 dark:bg-gray-700"></label>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <label class="text-xs font-medium text-gray-600 dark:text-gray-300">Litros<input v-model="review.litros" required type="number" min="0" step="0.01" inputmode="decimal" class="mt-1 min-h-11 w-full rounded-lg border p-2 dark:border-gray-600 dark:bg-gray-700"></label>
          <label class="text-xs font-medium text-gray-600 dark:text-gray-300">KM/Hora<input v-model="review.km_hora" required type="number" min="0" step="0.01" inputmode="decimal" class="mt-1 min-h-11 w-full rounded-lg border p-2 dark:border-gray-600 dark:bg-gray-700"></label>
        </div>
        <label class="block text-xs font-medium text-gray-600 dark:text-gray-300">Nº Remito<input v-model="review.remito" required type="text" inputmode="numeric" :pattern="isTicket ? '\\d{7}' : '\\d{6,7}'" :maxlength="isTicket ? 7 : 7" class="mt-1 min-h-11 w-full rounded-lg border p-2 font-mono dark:border-gray-600 dark:bg-gray-700"></label>
        <label class="block text-xs font-medium text-gray-600 dark:text-gray-300">Tanque (Pañol)<select v-model.number="review.paniol_id" class="mt-1 min-h-11 w-full rounded-lg border p-2 dark:border-gray-600 dark:bg-gray-700"><option :value="null">Seleccionar tanque</option><option v-for="pn in activeTanques" :key="pn.id" :value="pn.id">{{ pn.descripcion }}</option></select></label>

        <template v-if="isTicket">
          <label class="block text-xs font-medium text-gray-600 dark:text-gray-300">Proveedor<select v-model.number="review.proveedor_id" required class="mt-1 min-h-11 w-full rounded-lg border p-2 dark:border-gray-600 dark:bg-gray-700"><option :value="null">Seleccionar proveedor</option><option v-for="p in activeProviders" :key="p.id" :value="p.id">{{ p.razon_social || p.nombre || p.descripcion }}</option></select></label>
          <label class="block text-xs font-medium text-gray-600 dark:text-gray-300">Tipo de combustible<select v-model.number="review.tipo_combustible_id" class="mt-1 min-h-11 w-full rounded-lg border p-2 dark:border-gray-600 dark:bg-gray-700"><option :value="null">Seleccionar tipo</option><option v-for="t in activeTiposCombustible" :key="t.id" :value="t.id">{{ t.descripcion || t.nombre }}</option></select></label>
        </template>

        <template v-else-if="isRemito">
          <div class="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm dark:border-gray-600 dark:bg-gray-700/50">
            <div class="text-xs text-gray-500 dark:text-gray-400">Proveedor</div>
            <div class="font-semibold">{{ review.proveedor_nombre || 'INTERNO' }} <span class="text-xs font-normal text-gray-500">(asignado por el sistema)</span></div>
          </div>
          <label class="block text-xs font-medium text-gray-600 dark:text-gray-300">Tipo de combustible<select v-model.number="review.tipo_combustible_id" class="mt-1 min-h-11 w-full rounded-lg border p-2 dark:border-gray-600 dark:bg-gray-700"><option :value="null">Seleccionar tipo</option><option v-for="t in activeTiposCombustible" :key="t.id" :value="t.id">{{ t.descripcion || t.nombre }}</option></select></label>
        </template>

        <label class="block text-xs font-medium text-gray-600 dark:text-gray-300">Observaciones<textarea v-model="review.observaciones" rows="3" class="mt-1 w-full rounded-lg border p-2 dark:border-gray-600 dark:bg-gray-700"></textarea></label>
      </section>

      <section class="rounded-xl border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950/30">
        <h2 class="font-semibold">Configuración del viaje</h2>
        <p class="mt-1 text-xs text-blue-700 dark:text-blue-300">Se toma de Ajustes y no se reemplaza con lo leído en la foto.</p>
        <dl class="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm"><dt class="font-medium">Chofer</dt><dd>{{ configuredDriver }}</dd><dt class="font-medium">Patente</dt><dd>{{ settings?.patente }}</dd><dt class="font-medium">Unidad</dt><dd>{{ settings?.unidadNegocio?.descripcion }}</dd></dl>
      </section>

      <button type="submit" class="min-h-12 w-full rounded-xl bg-emerald-600 px-4 font-semibold text-white shadow hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-gray-400" :disabled="busy || state === 'confirming'">{{ state === 'confirming' ? 'Guardando…' : 'Confirmar y guardar' }}</button>
    </form>

    <section v-else-if="state === 'success'" class="space-y-4 text-center">
      <img v-if="previewUrl" :src="previewUrl" alt="Comprobante confirmado" class="max-h-[48vh] w-full rounded-xl bg-gray-100 object-contain shadow dark:bg-gray-800">
      <div class="rounded-xl border border-green-200 bg-green-50 p-5 dark:border-green-200 dark:bg-green-950/30"><div class="text-4xl" aria-hidden="true">✓</div><h2 class="mt-2 text-lg font-semibold">Carga registrada</h2><p class="mt-2 text-sm">ID movimiento: {{ result?.movimiento_id ?? result?.movement_id ?? 'confirmado' }}</p><p v-if="result?.imagen_id || result?.image_id" class="text-sm">ID imagen: {{ result?.imagen_id ?? result?.image_id }}</p></div>
      <button type="button" class="min-h-11 w-full rounded-lg bg-blue-600 px-4 font-medium text-white" @click="cancelAndGoBack">Volver a Combustible</button>
      <button type="button" class="min-h-11 w-full rounded-lg border border-gray-300 px-4" @click="reset">Cargar otra</button>
    </section>

    <section v-else-if="state === 'error'" class="space-y-4">
      <img v-if="previewUrl" :src="previewUrl" alt="Foto conservada para reintentar" class="max-h-[45vh] w-full rounded-xl bg-gray-100 object-contain shadow dark:bg-gray-800">
      <div class="rounded-xl border border-red-200 bg-red-50 p-4 text-red-900 dark:border-red-900 dark:bg-red-950/30 dark:text-red-100" role="alert"><h2 class="font-semibold">No se pudo completar la operación</h2><p class="mt-2 text-sm">{{ errorMessage }}</p></div>
      <button v-if="errorAction === 'settings'" type="button" class="min-h-11 w-full rounded-lg bg-blue-600 px-4 font-medium text-white" @click="router.push('/settings')">Ir a Ajustes</button>
      <button v-else-if="errorAction === 'retry'" type="button" class="min-h-11 w-full rounded-lg bg-blue-600 px-4 font-medium text-white" :disabled="busy" @click="retry">Reintentar</button>
      <button v-if="review" type="button" class="min-h-11 w-full rounded-lg border border-gray-300 px-4" @click="returnToReview">Volver a revisar</button>
      <button type="button" class="min-h-11 w-full rounded-lg border border-gray-300 px-4" @click="reset">Elegir otra foto</button>
    </section>
  </main>
</template>
