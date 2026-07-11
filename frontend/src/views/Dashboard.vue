<script setup>
const actions = [
  {
    to: '/new-trip',
    title: 'Registrar viaje',
    description: 'Cargar un nuevo viaje forestal.',
    color: 'border-blue-500',
  },
  {
    to: '/fuel-load',
    title: 'Carga de combustible',
    description: 'Registrar litros, camion, tanque y remito.',
    color: 'border-amber-500',
  },
  {
    to: '/carreton-move',
    title: 'Movimiento carreton',
    description: 'Registrar movimientos de carreton.',
    color: 'border-green-500',
  },
  {
    to: '/history',
    title: 'Historial',
    description: 'Revisar registros guardados y sincronizados.',
    color: 'border-slate-500',
  },
]
</script>

<template>
  <section class="mx-auto max-w-4xl px-4 py-5">
    <div class="mb-5 rounded-md border border-blue-100 bg-blue-50 p-4 text-blue-900 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-100">
      <h2 class="text-lg font-semibold">Registro de viajes Forestal Paraguay</h2>
      <p class="mt-1 text-sm">Selecciona una accion para empezar. La app mantiene los registros pendientes para sincronizar cuando haya conexion.</p>
    </div>

    <div class="grid gap-3 sm:grid-cols-2">
      <router-link
        v-for="action in actions"
        :key="action.to"
        :to="action.to"
        class="rounded-md border-l-4 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:bg-gray-800"
        :class="action.color"
      >
        <h3 class="font-semibold text-gray-900 dark:text-white">{{ action.title }}</h3>
        <p class="mt-1 text-sm text-gray-600 dark:text-gray-300">{{ action.description }}</p>
      </router-link>
    </div>
  </section>
</template>
