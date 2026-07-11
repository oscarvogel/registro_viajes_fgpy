<script setup>
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import { API_URL } from '../config'
import { useSyncStore } from '../stores/sync'
import {
  buildDefaultAdminDashboardRange,
  fetchAdminDashboardSummary,
  normalizeAdminDashboardSummary,
} from '../services/adminDashboard'

const syncStore = useSyncStore()
const loading = ref(false)
const error = ref('')
const range = ref(buildDefaultAdminDashboardRange())
const summary = ref(normalizeAdminDashboardSummary())

const pendingRecords = computed(() => syncStore.pendingRecords || [])
const blockedLocalRecords = computed(() => pendingRecords.value.filter((record) => record.blocked))
const kpis = computed(() => summary.value.kpis)

const formatNumber = (value) => Number(value || 0).toLocaleString('es-PY')
const formatDecimal = (value, digits = 2) => Number(value || 0).toLocaleString('es-PY', {
  minimumFractionDigits: digits,
  maximumFractionDigits: digits,
})

const loadSummary = async () => {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchAdminDashboardSummary({
      httpClient: axios,
      apiUrl: API_URL,
      filters: range.value,
    })
    summary.value = normalizeAdminDashboardSummary(data)
    await syncStore.loadPending()
  } catch (e) {
    error.value = e?.response?.status === 403
      ? 'No autorizado para ver el panel de transporte.'
      : 'No se pudo cargar el panel de transporte.'
  } finally {
    loading.value = false
  }
}

const rankingTitle = {
  por_equipo: 'Equipos destacados',
  por_chofer: 'Choferes destacados',
  por_unidad_negocio: 'Unidades de negocio',
}

onMounted(loadSummary)
</script>

<template>
  <div class="p-4 pb-20">
    <header class="mb-4">
      <h1 class="text-2xl font-bold dark:text-white">Panel de Transporte</h1>
      <p class="text-sm text-gray-500 mt-1">Indicadores operativos de viajes, carga y flota.</p>
    </header>

    <section class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow mb-4">
      <div class="grid grid-cols-2 gap-3">
        <label class="text-sm text-gray-700 dark:text-gray-200">
          <span class="block text-xs text-gray-500 mb-1">Desde</span>
          <input
            v-model="range.fecha_desde"
            type="date"
            class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white"
          >
        </label>
        <label class="text-sm text-gray-700 dark:text-gray-200">
          <span class="block text-xs text-gray-500 mb-1">Hasta</span>
          <input
            v-model="range.fecha_hasta"
            type="date"
            class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white"
          >
        </label>
      </div>
      <button
        type="button"
        class="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 rounded-lg font-medium shadow mt-4 disabled:bg-blue-300"
        :disabled="loading"
        @click="loadSummary"
      >
        {{ loading ? 'Cargando...' : 'Actualizar' }}
      </button>
      <div v-if="error" class="text-sm text-red-500 mt-2">{{ error }}</div>
    </section>

    <section class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
      <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow">
        <div class="text-xs text-gray-500">Viajes</div>
        <div class="text-2xl font-bold dark:text-white">{{ formatNumber(kpis.viajes) }}</div>
      </div>
      <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow">
        <div class="text-xs text-gray-500">Toneladas</div>
        <div class="text-2xl font-bold dark:text-white">{{ formatDecimal(kpis.toneladas) }}</div>
      </div>
      <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow">
        <div class="text-xs text-gray-500">Promedio por viaje</div>
        <div class="text-2xl font-bold dark:text-white">{{ formatDecimal(kpis.promedio_toneladas_por_viaje) }}</div>
      </div>
      <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow">
        <div class="text-xs text-gray-500">Litros cargados</div>
        <div class="text-2xl font-bold dark:text-white">{{ formatDecimal(kpis.litros) }}</div>
      </div>
      <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow">
        <div class="text-xs text-gray-500">Movimientos carretón</div>
        <div class="text-2xl font-bold dark:text-white">{{ formatNumber(kpis.movimientos_carreton) }}</div>
      </div>
      <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow lg:col-span-2">
        <div class="text-xs text-gray-500">Pendientes locales</div>
        <div class="text-2xl font-bold text-orange-600">{{ formatNumber(pendingRecords.length) }}</div>
      </div>
      <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow lg:col-span-2">
        <div class="text-xs text-gray-500">Bloqueados locales</div>
        <div class="text-2xl font-bold text-red-600">{{ formatNumber(blockedLocalRecords.length) }}</div>
      </div>
    </section>

    <section class="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-4">
      <div
        v-for="rankingKey in ['por_equipo', 'por_chofer', 'por_unidad_negocio']"
        :key="rankingKey"
        class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow"
      >
        <h2 class="font-semibold dark:text-white mb-3">{{ rankingTitle[rankingKey] }}</h2>
        <div v-if="summary.rankings[rankingKey].length === 0" class="text-sm text-gray-500">Sin datos en el período.</div>
        <div v-else class="space-y-3">
          <div
            v-for="item in summary.rankings[rankingKey]"
            :key="item.label"
            class="flex items-center justify-between gap-3 border-b border-gray-100 dark:border-gray-700 pb-2 last:border-b-0 last:pb-0"
          >
            <div>
              <div class="font-medium dark:text-white">{{ item.label }}</div>
              <div class="text-xs text-gray-500">{{ item.count }} registros</div>
            </div>
            <div class="text-sm font-semibold dark:text-white">{{ formatDecimal(item.total) }} Tn</div>
          </div>
        </div>
      </div>
    </section>

    <section class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow">
      <div class="flex items-start justify-between gap-3 mb-3">
        <div>
          <h2 class="font-semibold dark:text-white">Alertas operativas</h2>
          <p class="text-sm text-gray-500">Pendientes de sincronización de viajes y registros bloqueados en este dispositivo.</p>
        </div>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div class="rounded border border-orange-200 dark:border-orange-900 p-3">
          <div class="text-xs text-gray-500">Pendientes en este dispositivo</div>
          <div class="text-xl font-bold text-orange-600">{{ pendingRecords.length }}</div>
        </div>
        <div class="rounded border border-red-200 dark:border-red-900 p-3">
          <div class="text-xs text-gray-500">Bloqueados en este dispositivo</div>
          <div class="text-xl font-bold text-red-600">{{ blockedLocalRecords.length }}</div>
        </div>
      </div>

      <p v-if="summary.alerts.blocked_records_note" class="text-xs text-gray-500 mt-3">
        {{ summary.alerts.blocked_records_note }}
      </p>
    </section>
  </div>
</template>
