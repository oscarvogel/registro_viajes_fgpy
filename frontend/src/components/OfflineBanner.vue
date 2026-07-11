<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { clientLogger } from '@/services/logger'

const online = ref(navigator.onLine)
const updateAvailable = ref(false)

function trySync() {
  clientLogger.info('Usuario iniciÃ³ sincronizaciÃ³n manual', { event_type: 'user_action' })
  clientLogger.flush()
}

function reloadForUpdate() {
  // Try to reload to activate waiting SW
  window.location.reload()
}

function onOnline() {
  online.value = true
}

function onOffline() {
  online.value = false
}

function onSWUpdate() {
  updateAvailable.value = true
}

onMounted(() => {
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)
  window.addEventListener('sw:update', onSWUpdate)
})

onBeforeUnmount(() => {
  window.removeEventListener('online', onOnline)
  window.removeEventListener('offline', onOffline)
  window.removeEventListener('sw:update', onSWUpdate)
})
</script>

<template>
  <div aria-live="polite" class="fixed top-16 left-1/2 transform -translate-x-1/2 z-40 w-full max-w-2xl px-4">
    <div v-if="!online" role="status" class="mx-auto bg-yellow-50 border-l-4 border-yellow-400 text-yellow-700 p-3 rounded shadow">
      <div class="flex items-center justify-between gap-4">
        <div>
          <strong class="block">Sin conexiÃ³n</strong>
          <div class="text-sm">Tu dispositivo estÃ¡ sin conexiÃ³n. Los datos se guardarÃ¡n localmente y se sincronizarÃ¡n automÃ¡ticamente cuando vuelva la red.</div>
        </div>
        <div class="flex items-center gap-2">
          <button @click="trySync" class="bg-yellow-600 text-white px-3 py-1 rounded" aria-label="Reintentar sincronizaciÃ³n">Reintentar</button>
        </div>
      </div>
    </div>

    <div v-if="updateAvailable" role="status" class="mx-auto bg-blue-50 border-l-4 border-blue-400 text-blue-700 p-3 mt-2 rounded shadow">
      <div class="flex items-center justify-between gap-4">
        <div>
          <strong class="block">ActualizaciÃ³n disponible</strong>
          <div class="text-sm">Hay una nueva versiÃ³n de la aplicaciÃ³n. Recarga para aplicar la actualizaciÃ³n.</div>
        </div>
        <div class="flex items-center gap-2">
          <button @click="reloadForUpdate" class="bg-blue-600 text-white px-3 py-1 rounded" aria-label="Recargar aplicaciÃ³n">Recargar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sr-only:focus:not(.not-sr-only) { position: absolute; top: 1rem; left: 1rem; }
</style>
