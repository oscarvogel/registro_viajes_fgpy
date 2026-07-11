<template>
  <nav aria-label="Navegación principal" class="fixed bottom-0 w-full bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 pb-safe">
    <div class="flex justify-around items-center h-16" role="navigation">

      <router-link to="/dashboard" aria-label="Dashboard" class="flex flex-col items-center justify-center w-full h-full space-y-1" active-class="text-blue-600 dark:text-blue-400" :class="[$route.path === '/dashboard' ? 'text-blue-600' : 'text-gray-400']">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
        </svg>
        <span class="text-[10px] font-medium">Dashboard</span>
      </router-link>

      <router-link to="/new-trip" aria-label="Nuevo viaje" class="flex flex-col items-center justify-center w-full h-full space-y-1" active-class="text-blue-600 dark:text-blue-400" :class="[$route.path === '/new-trip' ? 'text-blue-600' : 'text-gray-400']">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        <span class="text-[10px] font-medium">Nuevo</span>
      </router-link>

      <router-link to="/fuel-load" aria-label="Registro de combustible" class="flex flex-col items-center justify-center w-full h-full space-y-1" active-class="text-blue-600 dark:text-blue-400" :class="[$route.path === '/fuel-load' ? 'text-blue-600' : 'text-gray-400']">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 13h2l1 2h12l1-2h2" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l2-6h10l2 6" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 17a2 2 0 104 0" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 17a2 2 0 104 0" />
        </svg>
        <span class="text-[10px] font-medium">Combustible</span>
      </router-link>

      <router-link to="/history" aria-label="Historial de viajes" class="flex flex-col items-center justify-center w-full h-full space-y-1" active-class="text-blue-600 dark:text-blue-400" :class="[$route.path === '/history' ? 'text-blue-600' : 'text-gray-400']">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span class="text-[10px] font-medium">Historial</span>
      </router-link>

      <router-link to="/settings" aria-label="Ajustes" class="flex flex-col items-center justify-center w-full h-full space-y-1" active-class="text-blue-600 dark:text-blue-400" :class="[$route.path === '/settings' ? 'text-blue-600' : 'text-gray-400']">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
        <span class="text-[10px] font-medium">Ajustes</span>
      </router-link>

    </div>
  </nav>
</template>
