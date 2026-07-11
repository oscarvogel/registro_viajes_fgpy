<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const version = import.meta.env.VITE_APP_VERSION || 'dev'

const title = computed(() => {
  const labels = {
    '/dashboard': 'Dashboard',
    '/new-trip': 'Nuevo viaje',
    '/fuel-load': 'Combustible',
    '/carreton-move': 'Carreton',
    '/history': 'Historial',
    '/settings': 'Ajustes',
    '/admin/dashboard': 'Admin',
    '/admin/logs': 'Logs',
  }
  return labels[route.path] || 'Viajes FGPY'
})
</script>

<template>
  <header class="sticky top-0 z-30 border-b border-gray-200 bg-white/95 backdrop-blur dark:border-gray-700 dark:bg-gray-900/95">
    <div class="mx-auto flex h-14 max-w-4xl items-center justify-between px-4">
      <div>
        <p class="text-xs font-semibold uppercase tracking-wide text-blue-700 dark:text-blue-300">Viajes FGPY</p>
        <h1 class="text-base font-semibold text-gray-900 dark:text-white">{{ title }}</h1>
      </div>
      <span class="rounded bg-gray-100 px-2 py-1 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-300">v{{ version }}</span>
    </div>
  </header>
</template>
