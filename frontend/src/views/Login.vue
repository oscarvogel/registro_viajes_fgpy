<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';
import Swal from 'sweetalert2';
import { API_URL, APP_VERSION } from '../config';
import { clientLogger } from '@/services/logger'
import { useSyncStore } from '@/stores/sync';
import { updateServiceWorkerAndDetectIndexChange } from '@/services/appUpdate';
import { loginAndNavigate } from '@/services/loginFlow';
import { safeConsole } from '@/services/safeConsole';

const dni = ref('');
const error = ref('');
const router = useRouter();

const checkAppVersionAfterLogin = async () => {
  try {
    const { data } = await axios.get(`${API_URL}/app-version`);
    const rawServer = (data?.release || 'unknown') + '';
    const rawClient = (APP_VERSION || 'unknown') + '';
    const normalize = (v) => v.replace(/\+.*$/, '').replace(/-.*/, '').trim();
    const serverRelease = normalize(rawServer) || 'unknown';
    const clientVersion = normalize(rawClient) || 'unknown';

    if (serverRelease === 'unknown' || clientVersion === 'unknown' || clientVersion.startsWith('dev') || serverRelease === clientVersion) {
      return;
    }

    const lastNotified = localStorage.getItem('last_notified_version');
    if (lastNotified === serverRelease) {
      return;
    }

    const online = navigator.onLine === undefined ? true : navigator.onLine;
    const text = online
      ? 'Hay una nueva version de la aplicacion en el servidor. Desea sincronizar y actualizar ahora?'
      : 'Hay una nueva version disponible, pero esta sin conexion. Se sincronizara cuando tenga senal.';

    const result = await Swal.fire({
      title: 'Actualizacion disponible',
      text,
      icon: 'info',
      showCancelButton: true,
      confirmButtonText: online ? 'Sincronizar ahora' : 'Ok',
      cancelButtonText: 'Continuar sin sincronizar',
    });

    try { localStorage.setItem('last_notified_version', serverRelease); } catch (e) { /* ignore */ }

    if (!result.isConfirmed || !online) {
      return;
    }

    const syncStore = useSyncStore();
    try {
      await syncStore.syncAll();

      if (navigator.serviceWorker && navigator.serviceWorker.getRegistration) {
        const reg = await navigator.serviceWorker.getRegistration();
        if (reg && typeof reg.update === 'function') {
          const swResult = await updateServiceWorkerAndDetectIndexChange(reg);
          if (swResult.changed) {
            await Swal.fire({
              title: 'Actualizacion detectada',
              text: 'Se detecto una nueva version de la app. Se recargara automaticamente.',
              icon: 'success',
              timer: 1200,
              showConfirmButton: false
            });
            window.location.reload();
            return;
          }
        }
      }

      await Swal.fire({ title: 'Sincronizacion', text: 'Sincronizacion completada. No se detectaron cambios de version en la app.', icon: 'info' });
    } catch (e) {
      safeConsole.error('Error durante sincronizacion forzada:', e?.message);
      await Swal.fire({ title: 'Error', text: 'No se pudo sincronizar completamente. Intente mas tarde.', icon: 'error' });
    }
  } catch (err) {
    safeConsole.warn('App version check failed', err?.message);
  }
}

const handleLogin = async () => {
  const result = await loginAndNavigate({
    dni: dni.value,
    apiUrl: API_URL,
    httpClient: axios,
    router,
    clientLogger,
    afterLogin: checkAppVersionAfterLogin,
    redirectTo: router.currentRoute.value.query.redirect,
  });

  if (!result.ok) {
    error.value = result.error;
    safeConsole.warn('Login error:', result.error);
  }
}
</script>

<template>
  <div class="flex flex-col items-center justify-center min-h-screen bg-white dark:bg-gray-900 p-4">
    <div class="w-full max-w-sm">
      <div class="flex justify-center mb-6">
        <img src="/logo.png" alt="Logo" class="w-28 h-auto object-contain" />
      </div>

      <h1 class="text-2xl font-bold text-center mb-2 dark:text-white">Bienvenido</h1>
      <p class="text-center text-gray-500 mb-8">Ingresa tu DNI para comenzar</p>

      <form @submit.prevent="handleLogin" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">DNI o Cedula</label>
          <input
            v-model="dni"
            type="text"
            inputmode="numeric"
            placeholder="12345678"
            class="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-800 dark:border-gray-700 dark:text-white"
            required
          >
        </div>

        <div v-if="error" class="text-red-500 text-sm center">{{ error }}</div>

        <button
          type="submit"
          class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 rounded-lg transition-colors"
        >
          Ingresar
        </button>
      </form>
    </div>
  </div>
</template>
