<script setup>
import { onMounted, ref } from 'vue'
import axios from 'axios'
import { API_URL } from '@/config'
import { buildClientLogCsv, fetchClientLogSummary, getCategoryEntries } from '@/services/adminLogs'

const loading = ref(false)
const error = ref('')
const summary = ref({ count: 0, items: [], categories: {} })

const loadLogs = async () => {
  loading.value = true
  error.value = ''
  try {
    summary.value = await fetchClientLogSummary({
      httpClient: axios,
      apiUrl: API_URL,
    })
  } catch (e) {
    error.value = e?.response?.data?.detail || e?.message || 'No se pudieron cargar los logs.'
  } finally {
    loading.value = false
  }
}

const downloadCsv = () => {
  const blob = new Blob([buildClientLogCsv(summary.value.items || [])], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'client-logs.csv'
  link.click()
  URL.revokeObjectURL(url)
}

onMounted(loadLogs)
</script>

<template>
  <section class="mx-auto max-w-5xl px-4 py-5">
    <div class="mb-4 flex items-center justify-between gap-3">
      <div>
        <h2 class="text-xl font-semibold">Logs frontend</h2>
        <p class="text-sm text-gray-600 dark:text-gray-300">Resumen de errores y advertencias reportados por clientes.</p>
      </div>
      <button class="fg-btn-blue" :disabled="loading" @click="loadLogs">Actualizar</button>
    </div>

    <div v-if="error" class="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</div>

    <div class="fg-card p-4">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p class="text-sm text-gray-500">Total</p>
          <p class="text-2xl font-bold">{{ summary.count || 0 }}</p>
        </div>
        <button class="fg-btn-secondary" :disabled="!(summary.items || []).length" @click="downloadCsv">Exportar CSV</button>
      </div>

      <div v-if="loading" class="text-sm text-gray-500">Cargando...</div>
      <div v-else-if="!(summary.items || []).length" class="text-sm text-gray-500">No hay logs para mostrar.</div>

      <div v-else class="space-y-3">
        <article v-for="(item, index) in summary.items" :key="index" class="rounded-md border border-gray-200 p-3 dark:border-gray-700">
          <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p class="text-sm font-semibold">{{ item.timestamp || 'Sin fecha' }}</p>
            <span class="rounded bg-gray-100 px-2 py-1 text-xs dark:bg-gray-700">{{ item.summary?.errors || 0 }} errores</span>
          </div>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="[category, count] in getCategoryEntries(item.summary)"
              :key="category"
              class="rounded bg-blue-50 px-2 py-1 text-xs text-blue-700 dark:bg-blue-950 dark:text-blue-200"
            >
              {{ category }}: {{ count }}
            </span>
          </div>
          <p v-if="item.samples?.[0]?.message" class="mt-2 text-sm text-gray-600 dark:text-gray-300">{{ item.samples[0].message }}</p>
        </article>
      </div>
    </div>
  </section>
</template>
