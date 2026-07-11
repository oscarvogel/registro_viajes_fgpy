<script setup>
defineProps({
  show: { type: Boolean, default: false },
  platform: { type: String, default: 'desktop' },
})

defineEmits(['close'])
</script>

<template>
  <div v-if="show" class="fixed inset-0 z-50 flex items-end bg-black/40 p-4 sm:items-center sm:justify-center">
    <section class="w-full rounded-t-lg bg-white p-5 shadow-xl dark:bg-gray-800 sm:max-w-md sm:rounded-lg">
      <div class="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white">Instalar aplicacion</h2>
          <p class="mt-1 text-sm text-gray-600 dark:text-gray-300">Guarda el acceso en la pantalla de inicio para usarla mas rapido.</p>
        </div>
        <button class="rounded px-2 py-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700" @click="$emit('close')">Cerrar</button>
      </div>

      <ol v-if="platform === 'ios'" class="list-decimal space-y-2 pl-5 text-sm text-gray-700 dark:text-gray-200">
        <li>Abre esta pagina en Safari.</li>
        <li>Toca el boton compartir.</li>
        <li>Elige "Agregar a inicio".</li>
        <li>Confirma con "Agregar".</li>
      </ol>
      <p v-else class="text-sm text-gray-700 dark:text-gray-200">
        Usa el boton de instalacion de Ajustes cuando el navegador lo habilite.
      </p>
    </section>
  </div>
</template>
