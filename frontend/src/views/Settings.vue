<script setup>
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import { useCatalogStore } from '../stores/catalog';
import { useSyncStore } from '../stores/sync';
import { useInstallPrompt } from '../composables/useInstallPrompt';
import InstallPrompt from '../components/InstallPrompt.vue';
import Swal from 'sweetalert2';
import { API_URL, APP_VERSION } from '../config';
import { updateServiceWorkerAndDetectIndexChange } from '@/services/appUpdate';
import { clearStoredSession } from '@/services/session';
import { isAdminSession } from '@/services/adminAccess';
import { safeConsole } from '@/services/safeConsole';
import { clientLogger } from '@/services/logger';

const router = useRouter();
const catalog = useCatalogStore();
const syncStore = useSyncStore();
const syncing = ref(false);
const syncMessage = ref('');
const syncSuccess = ref(false);

const catalogLoading = ref(false);
const catalogMessage = ref('');
const catalogSuccess = ref(false);
const defaultPatente = ref('');
const defaultUnidadNegocio = ref('');
const isAdmin = computed(() => isAdminSession());

// Sistema de instalaciÃ³n mejorado
const {
    canInstall,
    isInstalled,
    platform,
    showIOSInstructions,
    promptInstall,
    closeIOSInstructions,
    isIOSSafari
} = useInstallPrompt();

const installMessage = ref('');
const showInstructions = ref(false);

// Texto del botÃ³n segÃºn la plataforma
const installButtonText = computed(() => {
    if (isInstalled.value) return 'App instalada âœ“';
    if (platform.value === 'ios') return 'Ver instrucciones de instalaciÃ³n';
    return 'Instalar app';
});

// Mensaje de estado
const installStatusMessage = computed(() => {
    if (isInstalled.value) return 'La app ya estÃ¡ instalada en tu dispositivo';
    if (platform.value === 'ios' && !isIOSSafari) {
        return 'Para instalar en iPhone/iPad, abre esta pÃ¡gina en Safari';
    }
    if (!canInstall.value && !isInstalled.value) {
        return 'La instalaciÃ³n no estÃ¡ disponible en este momento';
    }
    return '';
});

onMounted(async () => {
    // Ensure catalog is loaded
    if (catalog.equipos.length === 0) {
        await catalog.fetchCatalogues();
    }
    defaultPatente.value = localStorage.getItem('default_patente') || '';
    defaultUnidadNegocio.value = localStorage.getItem('default_unidad_negocio') || '';
});

const saveDefaultPatente = () => {
    localStorage.setItem('default_patente', defaultPatente.value);
};

const saveDefaultUnidadNegocio = () => {
    localStorage.setItem('default_unidad_negocio', defaultUnidadNegocio.value);
};

const logout = () => {
    clearStoredSession();
    clientLogger.clearUserId();
    router.replace('/login');
};

const toggleDarkMode = () => {
  if (document.documentElement.classList.contains('dark')) {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('color-theme', 'light');
  } else {
      document.documentElement.classList.add('dark');
      localStorage.setItem('color-theme', 'dark');
  }
}

const handleInstallClick = async () => {
    installMessage.value = '';

    if (platform.value === 'ios') {
        // En iOS, mostrar las instrucciones
        showInstructions.value = true;
        return;
    }

    // Android/Desktop - usar el prompt nativo
    const result = await promptInstall();

    if (result.outcome === 'accepted') {
        installMessage.value = 'Instalando...';
        setTimeout(() => {
            installMessage.value = 'App instalada correctamente';
        }, 1000);
    } else if (result.outcome === 'dismissed') {
        installMessage.value = 'InstalaciÃ³n cancelada';
    } else if (result.outcome === 'unavailable') {
        installMessage.value = 'InstalaciÃ³n no disponible';
    }
};

const doSync = async () => {
    syncing.value = true;
    syncMessage.value = 'Sincronizando...';
    try {
        syncSuccess.value = false;
        let result = {};
        if (typeof syncStore.syncAll === 'function') {
            result = await syncStore.syncAll() || {};
        } else {
            // Fallback: dynamic import in case HMR changed the module
            const mod = await import('../stores/sync');
            const fresh = mod.useSyncStore();
            if (typeof fresh.syncAll === 'function') {
                result = await fresh.syncAll() || {};
            } else {
                throw new Error('syncAll not available');
            }
        }

        const empCount = result.empleados ?? 0;
        const provCount = result.proveedores ?? 0;
        const eqCount = result.equipos ?? 0;
        const panCount = result.panioles ?? 0;
        const unCount = result.unidadesNegocio ?? 0;
        syncMessage.value = `SincronizaciÃ³n completada â€” Empleados: ${empCount}, Proveedores: ${provCount}, Equipos: ${eqCount}, PaÃ±oles: ${panCount}, UN: ${unCount}`;
        syncSuccess.value = true;
    } catch (e) {
        safeConsole.error('Sync failed', e?.message);
        syncMessage.value = 'Error de sincronizaciÃ³n';
    } finally {
        setTimeout(() => {
            syncing.value = false;
            // clear message after short delay
            setTimeout(() => {
                syncMessage.value = '';
                syncSuccess.value = false;
            }, 2000);
        }, 500);
    }
}

const doForceFullSync = async () => {
    // Check server app-version and prompt user to sync + update assets
    try {
        const res = await fetch(`${API_URL}/app-version`);
        const data = await res.json();
        const rawServer = (data?.release || 'unknown') + '';
        const rawClient = (APP_VERSION || 'unknown') + '';
        const normalize = (v) => v.replace(/\+.*$/, '').replace(/-.*/, '').trim();
        const serverRelease = normalize(rawServer) || 'unknown';
        const clientVersion = normalize(rawClient) || 'unknown';

        if (serverRelease !== 'unknown' && clientVersion !== 'unknown' && serverRelease === clientVersion) {
            await Swal.fire({ title: 'SincronizaciÃ³n', text: 'La app en este dispositivo ya coincide con la versiÃ³n del servidor.', icon: 'info' });
            return;
        }

        const online = navigator.onLine === undefined ? true : navigator.onLine;
        if (!online) {
            await Swal.fire({ title: 'SincronizaciÃ³n', text: 'Hay una actualizaciÃ³n disponible pero el dispositivo estÃ¡ sin conexiÃ³n. ConÃ©ctese y vuelva a intentar.', icon: 'warning' });
            return;
        }

        const confirm = await Swal.fire({
            title: 'Actualizar aplicaciÃ³n',
            text: 'Se detectÃ³ una nueva versiÃ³n en el servidor. Se realizarÃ¡ la sincronizaciÃ³n de datos y se intentarÃ¡ actualizar la app. Â¿Desea continuar?',
            icon: 'question',
            showCancelButton: true,
            confirmButtonText: 'SÃ­, actualizar',
            cancelButtonText: 'Cancelar'
        });

        if (!confirm.isConfirmed) return;

        // First sync data and catalogs
        await doSync();

        // Attempt service worker update to fetch new frontend assets
        try {
            if (navigator.serviceWorker && navigator.serviceWorker.getRegistration) {
                const reg = await navigator.serviceWorker.getRegistration();
                if (reg && typeof reg.update === 'function') {
                    const swResult = await updateServiceWorkerAndDetectIndexChange(reg);
                    if (swResult.changed) {
                        await Swal.fire({
                            title: 'ActualizaciÃ³n detectada',
                            text: 'Se detectÃ³ una nueva versiÃ³n de la app. Se recargarÃ¡ automÃ¡ticamente.',
                            icon: 'success',
                            timer: 1200,
                            showConfirmButton: false
                        });
                        window.location.reload();
                        return;
                    }
                }
            }
            await Swal.fire({ title: 'Hecho', text: 'SincronizaciÃ³n completada. No se detectaron cambios de versiÃ³n en la app.', icon: 'info' });
        } catch (err) {
            safeConsole.warn('Service worker update failed', err?.message);
            await Swal.fire({ title: 'SincronizaciÃ³n', text: 'SincronizaciÃ³n completada pero no se pudo actualizar automÃ¡ticamente el servicio. Recargue manualmente.', icon: 'warning' });
        }
    } catch (e) {
        safeConsole.error('Force full sync failed', e?.message);
        await Swal.fire({ title: 'Error', text: 'No se pudo comprobar la versiÃ³n del servidor. Intente mÃ¡s tarde.', icon: 'error' });
    }
}

const doFetchCatalogues = async () => {
    catalogLoading.value = true;
    catalogSuccess.value = false;
    catalogMessage.value = 'Actualizando catÃ¡logos...';
    try {
        const res = await catalog.fetchCatalogues();
        const empCount = res?.empleados ?? 0;
        const provCount = res?.proveedores ?? 0;
        const eqCount = res?.equipos ?? 0;
        const panCount = res?.panioles ?? 0;
        const unCount = res?.unidadesNegocio ?? 0;
        catalogMessage.value = `CatÃ¡logos actualizados â€” Empleados: ${empCount}, Proveedores: ${provCount}, Equipos: ${eqCount}, PaÃ±oles: ${panCount}, UN: ${unCount}`;
        catalogSuccess.value = true;
    } catch (e) {
        safeConsole.error('Catalog update failed', e?.message);
        catalogMessage.value = 'Error al actualizar catÃ¡logos';
    } finally {
        catalogLoading.value = false;
        setTimeout(() => {
            catalogMessage.value = '';
            catalogSuccess.value = false;
        }, 2000);
    }
}
</script>

<template>
  <div class="p-4">
    <h1 class="text-2xl font-bold mb-4">Ajustes</h1>

    <div class="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden space-y-1">
        <div class="p-4 border-b dark:border-gray-700 flex justify-between items-center bg-gray-50 dark:bg-gray-700">
            <span>Modo Oscuro</span>
            <button @click="toggleDarkMode" class="bg-gray-200 dark:bg-gray-600 px-3 py-1 rounded">Cambiar</button>
        </div>

        <div class="p-4 border-b dark:border-gray-700">
            <label class="block text-xs font-medium text-gray-500 mb-1">VehÃ­culo Predeterminado</label>
            <select v-model="defaultPatente" @change="saveDefaultPatente" class="w-full p-2 rounded border dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                <option value="">Sin defecto</option>
                <option v-for="e in catalog.equipos.filter(x => x.tipo_movil_id === 4)" :key="e.id" :value="e.patente">{{ e.descripcion }} ({{ e.patente }})</option>
            </select>
        </div>

        <div class="p-4 border-b dark:border-gray-700">
            <label class="block text-xs font-medium text-gray-500 mb-1">Unidad de Negocio Predeterminada</label>
            <select v-model="defaultUnidadNegocio" @change="saveDefaultUnidadNegocio" class="w-full p-2 rounded border dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                <option value="">Sin defecto</option>
                <option v-for="un in catalog.unidadesNegocio" :key="un.id" :value="un.id">{{ un.descripcion }} ({{ un.prefijo }})</option>
            </select>
        </div>

        <div class="p-4 border-b dark:border-gray-700 flex items-center justify-between gap-4">
            <div>
                <div class="font-medium">Movimiento de carretÃ³n</div>
                <div class="text-sm text-gray-500 mt-1">Registrar KM inicial/final, estado y mÃ¡quina transportada.</div>
            </div>
            <button @click="router.push('/carreton-move')" class="bg-amber-600 hover:bg-amber-700 text-white font-medium py-2 px-4 rounded">
                Abrir
            </button>
        </div>

        <div class="p-4 border-b dark:border-gray-700">
            <div class="flex items-start gap-3 mb-3">
                <div class="flex-shrink-0 mt-1">
                    <svg class="w-6 h-6 text-emerald-600 dark:text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                    </svg>
                </div>
                <div class="flex-1">
                    <div class="font-medium">Instalar aplicaciÃ³n</div>
                    <div class="text-sm text-gray-500 mt-1">
                        Instala la app para acceso rÃ¡pido y funcionamiento offline.
                    </div>
                    <div v-if="platform === 'ios'" class="mt-2 text-xs text-blue-600 dark:text-blue-400 flex items-center gap-1">
                        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" />
                        </svg>
                        <span>Detectado: iPhone/iPad</span>
                    </div>
                </div>
            </div>

            <button
                @click="handleInstallClick"
                :disabled="!canInstall || isInstalled"
                class="w-full bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-medium py-3 px-3 rounded flex items-center justify-center gap-2 transition-colors"
            >
                <svg v-if="!isInstalled" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                <svg v-else class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 00-1.414 0L8 12.586 4.707 9.293a1 1 0 10-1.414 1.414l4 4a1 1 0 001.414 0l8-8a1 1 0 000-1.414z" clip-rule="evenodd" />
                </svg>
                {{ installButtonText }}
            </button>

            <div v-if="installStatusMessage" class="text-sm text-gray-600 dark:text-gray-400 mt-2 text-center">
                {{ installStatusMessage }}
            </div>
            <div v-if="installMessage" class="text-sm font-medium mt-2 text-center" :class="isInstalled ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-600 dark:text-gray-400'">
                {{ installMessage }}
            </div>
        </div>

        <div class="p-4 border-b dark:border-gray-700">
            <div class="font-medium">SincronizaciÃ³n</div>
            <div class="text-sm text-gray-500 mb-3">Estado: {{ catalog.isOffline ? 'Offline' : 'Conectado' }}</div>
            <div class="flex gap-2">
                <button @click="doForceFullSync" :disabled="syncing || catalogLoading" class="flex-1 bg-amber-600 hover:bg-amber-700 text-white font-medium py-2 px-3 rounded flex items-center justify-center gap-2">
                    <svg v-if="!(syncing || catalogLoading)" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                        <path d="M8 3a5 5 0 00-4.546 2.916A4 4 0 108 15H7a1 1 0 000 2h4a1 1 0 100-2h-1a3 3 0 110-6h.26A5 5 0 108 3z" />
                    </svg>
                    <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <circle cx="12" cy="12" r="10" stroke-width="4" stroke-opacity="0.25"></circle>
                        <path d="M22 12a10 10 0 00-10-10" stroke-width="4"></path>
                    </svg>
                    <span v-if="!(syncing || catalogLoading)">Sincronizar y actualizar</span>
                    <span v-else>Procesando...</span>
                    <svg v-if="syncSuccess" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-green-300 ml-2" viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 00-1.414 0L8 12.586 4.707 9.293a1 1 0 10-1.414 1.414l4 4a1 1 0 001.414 0l8-8a1 1 0 000-1.414z" clip-rule="evenodd" />
                    </svg>
                </button>
            </div>
            <div v-if="syncMessage" class="text-sm text-gray-600 mt-2">{{ syncMessage }}</div>
        </div>
        <div v-if="isAdmin" class="p-4 border-b dark:border-gray-700 flex items-center justify-between gap-4">
            <div>
                <div class="font-medium">Panel de transporte</div>
                <div class="text-sm text-gray-500 mt-1">Viajes, carga, flota y alertas operativas.</div>
            </div>
            <button @click="router.push('/admin/dashboard')" class="bg-blue-700 hover:bg-blue-800 text-white font-medium py-2 px-4 rounded">
                Abrir
            </button>
        </div>
        <div class="p-4">
            <button class="text-red-500 w-full text-left" @click="logout">Cerrar SesiÃ³n</button>
        </div>
    </div>

    <!-- Modal de instrucciones de instalaciÃ³n -->
    <InstallPrompt
        :show="showInstructions || showIOSInstructions"
        :platform="platform"
        @close="showInstructions = false; closeIOSInstructions()"
    />
  </div>
</template>
