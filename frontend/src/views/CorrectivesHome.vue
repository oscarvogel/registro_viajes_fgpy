<script setup>
import Swal from 'sweetalert2'

const historialPendiente = () => {
  Swal.fire({
    icon: 'info',
    title: 'Historial de correctivos',
    text: 'La consulta de historial se incorpora en el siguiente bloque de implementación (#32).',
    confirmButtonColor: '#2563eb',
  })
}
</script>

<template>
  <section class="mx-auto max-w-3xl px-4 py-5 pb-24">
    <div class="mb-5 rounded-xl border border-rose-100 bg-rose-50 p-4 dark:border-rose-900/60 dark:bg-rose-950/30">
      <p class="text-xs font-semibold uppercase tracking-wide text-rose-700 dark:text-rose-300">Mantenimiento</p>
      <h2 class="mt-1 text-xl font-bold text-gray-900 dark:text-white">Correctivos</h2>
      <p class="mt-1 text-sm text-gray-600 dark:text-gray-300">Registra incidencias y trabajos realizados sobre camiones y equipos.</p>
    </div>

    <div class="grid gap-4 sm:grid-cols-2">
      <router-link to="/correctivos/nuevo" class="rounded-xl border-l-4 border-rose-500 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:bg-gray-800">
        <div class="text-2xl" aria-hidden="true">🛠️</div>
        <h3 class="mt-3 text-lg font-semibold text-gray-900 dark:text-white">Registrar correctivo</h3>
        <p class="mt-1 text-sm text-gray-600 dark:text-gray-300">Cargar incidencia, trabajo realizado, proveedor, repuestos y costos opcionales.</p>
      </router-link>

      <button type="button" @click="historialPendiente" class="rounded-xl border-l-4 border-slate-400 bg-white p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:bg-gray-800">
        <div class="text-2xl" aria-hidden="true">📋</div>
        <h3 class="mt-3 text-lg font-semibold text-gray-900 dark:text-white">Ver historial</h3>
        <p class="mt-1 text-sm text-gray-600 dark:text-gray-300">Consultar intervenciones anteriores por equipo. Disponible al completar el #32.</p>
      </button>
    </div>
  </section>
</template>
