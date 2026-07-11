<script setup>
import { computed, ref, onMounted } from 'vue';
import { useCatalogStore } from '../stores/catalog';
import Swal from 'sweetalert2';
import axios from 'axios';
import { useSyncStore } from '../stores/sync';
import { API_URL } from '../config';

const syncStore = useSyncStore();
const catalog = useCatalogStore();

const fechaDesde = ref('');
const fechaHasta = ref('');
const historial = ref([]);
const movimientosCarreton = ref([]);
const loading = ref(false);
const error = ref('');
const activeTab = ref('viajes');

const formatDate = (isoDate) => {
    if (!isoDate) return '';
    const [y, m, d] = isoDate.split('-');
    return `${d}/${m}/${y}`;
};

const formatTime = (timeValue) => {
    if (!timeValue) return '';
    return String(timeValue).slice(0, 5);
};

const formatTn = (value) => {
    const num = Number(value || 0);
    return `${num.toFixed(2)} Tn`;
};

const getHistorial = () => (Array.isArray(historial.value) ? historial.value : []);
const totalViajes = () => getHistorial().length;
const getMovimientosCarreton = () => (Array.isArray(movimientosCarreton.value) ? movimientosCarreton.value : []);
const totalMovimientosCarreton = () => getMovimientosCarreton().length;
const totalTn = () => {
    const sum = getHistorial().reduce((acc, item) => acc + Number(item.produccion || 0), 0);
    return sum;
};
const pendingViajes = computed(() => syncStore.pendingRecords.filter(r => (r.record_type || 'viaje') === 'viaje'));
const pendingCarreton = computed(() => syncStore.pendingRecords.filter(r => r.record_type === 'carreton'));

const setDefaultRange = () => {
    const today = new Date();
    const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
    const toIso = (d) => d.toISOString().split('T')[0];
    fechaDesde.value = toIso(firstDay);
    fechaHasta.value = toIso(today);
};

const loadHistorial = async () => {
    error.value = '';
    historial.value = [];
    movimientosCarreton.value = [];

    const userStr = localStorage.getItem('user');
    if (!userStr) {
        error.value = 'No hay un chofer logueado.';
        return;
    }

    if (!fechaDesde.value || !fechaHasta.value) {
        error.value = 'Seleccione un rango de fechas.';
        return;
    }

    const user = JSON.parse(userStr);
    loading.value = true;
    try {
        const [viajesRes, carretonRes] = await Promise.all([
            axios.get(`${API_URL}/historial-viajes`, {
                params: {
                    chofer_id: user.id,
                    fecha_desde: fechaDesde.value,
                    fecha_hasta: fechaHasta.value
                }
            }),
            axios.get(`${API_URL}/movimientos-carreton`, {
                params: {
                    chofer_id: user.id,
                    fecha_desde: fechaDesde.value,
                    fecha_hasta: fechaHasta.value
                }
            })
        ]);
        historial.value = Array.isArray(viajesRes.data) ? viajesRes.data : (viajesRes.data?.items ?? []);
        movimientosCarreton.value = Array.isArray(carretonRes.data) ? carretonRes.data : (carretonRes.data?.items ?? []);
    } catch (e) {
        error.value = 'No se pudo cargar el historial.';
    } finally {
        loading.value = false;
    }
};

onMounted(async () => {
    await catalog.fetchCatalogues();
    await syncStore.loadPending();
    setDefaultRange();
    await loadHistorial();
});

const normalizePatente = (value) => String(value || '').replace(/\s+/g, '').toUpperCase();

const currentEquipoId = computed(() => {
    const defaultPatente = localStorage.getItem('default_patente');
    if (!defaultPatente || !catalog.equipos) return null;
    const target = normalizePatente(defaultPatente);
    const found = catalog.equipos.find(e => normalizePatente(e.patente) === target || normalizePatente(e.patente.replace(/\s+/g, '')) === target);
    return found ? found.id : null;
});

const pendingForCurrent = computed(() => {
    if (!currentEquipoId.value) return [];
    return syncStore.pendingRecords.filter(r => (r.record_type === 'carreton') && Number(r.equipo_id) === Number(currentEquipoId.value));
});

const confirmRemove = async (record) => {
    const res = await Swal.fire({
        title: 'Eliminar registro pendiente?',
        text: 'Se eliminarÃ¡ el registro local y no podrÃ¡ recuperarse. Â¿Continuar?',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'SÃ­, eliminar',
        cancelButtonText: 'Cancelar',
        confirmButtonColor: '#DC2626'
    });
    if (res.isConfirmed) {
        const r = await syncStore.removePending(record.local_id);
        if (r.removed) {
            Swal.fire({ title: 'Eliminado', icon: 'success', timer: 1200, showConfirmButton: false });
        } else {
            Swal.fire({ title: 'Error', text: 'No se pudo eliminar el registro', icon: 'error' });
        }
    }
};
</script>

<template>
  <div class="p-4 pb-20">
    <h1 class="text-2xl font-bold mb-4">Historial</h1>

        <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow mb-6">
            <div class="grid grid-cols-2 gap-3">
                <div>
                    <label class="block text-xs font-medium text-gray-500 mb-1">Desde</label>
                    <input v-model="fechaDesde" type="date" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
                </div>
                <div>
                    <label class="block text-xs font-medium text-gray-500 mb-1">Hasta</label>
                    <input v-model="fechaHasta" type="date" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
                </div>
            </div>
            <button @click="loadHistorial" class="w-full bg-blue-600 text-white py-2 rounded-lg font-medium shadow mt-4">
                Buscar viajes
            </button>
            <div v-if="error" class="text-sm text-red-500 mt-2">{{ error }}</div>
        </div>

    <!-- Pending / Offline Records -->
    <div v-if="syncStore.pendingRecords.length > 0" class="mb-6">
        <h2 class="text-sm font-semibold text-orange-600 mb-2">Pendientes de SincronizaciÃ³n</h2>
         <div v-for="record in syncStore.pendingRecords" :key="record.local_id" class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow mb-3" :class="record.blocked ? 'border-l-4 border-red-500' : 'border-l-4 border-orange-500'">
            <div class="flex justify-between items-start">
                <div>
                    <div class="font-bold">{{ record.record_type === 'carreton' ? (record.tipo_maquina_transportada || 'Movimiento de carretÃ³n') : record.patente }}</div>
                    <div class="text-sm text-gray-500">
                        {{ record.record_type === 'carreton'
                            ? `${record.estado_carga} â€¢ KM ${Number(record.km_inicial).toFixed(2)} a ${Number(record.km_final).toFixed(2)}`
                            : record.numero_remision }}
                    </div>
                    <div v-if="record.record_type === 'carreton' && record.hora_inicio_viaje" class="text-xs text-gray-400 mt-1">
                        Inicio viaje: {{ formatTime(record.hora_inicio_viaje) }}
                    </div>
                </div>
                <div class="text-right">
                    <div class="font-mono">{{ record.record_type === 'carreton' ? 'CarretÃ³n' : `${(record.peso_bruto_origen - record.tara_origen).toFixed(2)} Tn` }}</div>
                    <div class="text-xs" :class="record.blocked ? 'text-red-500' : 'text-orange-500'">{{ record.blocked ? 'Bloqueado' : 'Pendiente' }}</div>
                </div>
            </div>
                <div v-if="record.blocked_reason" class="mt-3 rounded-lg bg-red-50 text-red-700 px-3 py-2 text-xs">
                    {{ record.blocked_reason }}
                </div>
                <div class="flex gap-2 mt-3">
                    <button @click="confirmRemove(record)" class="text-sm px-3 py-1 rounded bg-red-600 text-white">Eliminar</button>
                    <button v-if="!record.blocked" @click="syncStore.syncPending()" class="text-sm px-3 py-1 rounded bg-blue-600 text-white">Reintentar</button>
                </div>
        </div>
    </div>

    <div class="grid grid-cols-2 gap-3 mb-6">
        <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow flex items-center gap-3">
            <div class="w-10 h-10 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 8v8" />
                    <path d="M8 12h8" />
                    <path d="M3 21h18" />
                    <path d="M5 21V7a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v14" />
                </svg>
            </div>
            <div>
                <div class="text-xs text-gray-500">Viajes en el perÃ­odo</div>
                <div class="text-2xl font-bold">{{ totalViajes() }}</div>
            </div>
        </div>
        <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow flex items-center gap-3">
            <div class="w-10 h-10 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M20 7h-9" />
                    <path d="M14 17H5" />
                    <circle cx="7" cy="7" r="3" />
                    <circle cx="17" cy="17" r="3" />
                </svg>
            </div>
            <div>
                <div class="text-xs text-gray-500">TN totales transportadas</div>
                <div class="text-2xl font-bold">{{ formatTn(totalTn()) }}</div>
            </div>
        </div>
        <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow flex items-center gap-3">
            <div class="w-10 h-10 rounded-full bg-amber-100 text-amber-600 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M3 17h18" />
                    <path d="M6 17V9l4-3 4 3v8" />
                    <path d="M14 12h6l1 2v3" />
                </svg>
            </div>
            <div>
                <div class="text-xs text-gray-500">Movimientos carretÃ³n</div>
                <div class="text-2xl font-bold">{{ totalMovimientosCarreton() }}</div>
                <div v-if="currentEquipoId" class="text-xs text-gray-400 mt-1">Pendientes para el mÃ³vil actual: <span class="font-semibold text-amber-600">{{ pendingForCurrent.length }}</span></div>
            </div>
        </div>
        <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow flex items-center gap-3">
            <div class="w-10 h-10 rounded-full bg-orange-100 text-orange-600 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 20V10" />
                    <path d="m18 20-6-6-6 6" />
                    <path d="M4 4h16" />
                </svg>
            </div>
            <div>
                <div class="text-xs text-gray-500">Pendientes offline</div>
                <div class="text-2xl font-bold">{{ pendingViajes.length + pendingCarreton.length }}</div>
                <div v-if="syncStore.pendingRecords.some(record => record.blocked)" class="text-xs text-red-500 mt-1">Hay registros bloqueados que requieren revisiÃ³n.</div>
            </div>
        </div>
    </div>

    <div class="flex gap-2 mb-4">
        <button @click="activeTab = 'viajes'" :class="activeTab === 'viajes' ? 'bg-blue-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300'" class="flex-1 py-2 rounded-lg font-medium shadow">
            Viajes
        </button>
        <button @click="activeTab = 'carreton'" :class="activeTab === 'carreton' ? 'bg-amber-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300'" class="flex-1 py-2 rounded-lg font-medium shadow">
            CarretÃ³n
        </button>
    </div>

    <div v-if="loading" class="text-center text-sm text-gray-500">Cargando...</div>
    <div v-else-if="activeTab === 'viajes'" class="space-y-3">
        <div v-if="historial.length === 0" class="text-center text-sm text-gray-500">No hay viajes en este rango.</div>
                <div v-for="item in historial" :key="item.id" class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow">
            <div class="flex justify-between items-start">
                <div>
                                        <div class="font-bold flex items-center gap-2">
                                            <span class="inline-flex items-center justify-center w-7 h-7 rounded-full bg-slate-100 text-slate-600">
                                                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                                    <path d="M3 13h2l1 2h12l1-2h2" />
                                                    <path d="M5 13l2-6h10l2 6" />
                                                    <circle cx="7.5" cy="17" r="1.5" />
                                                    <circle cx="16.5" cy="17" r="1.5" />
                                                </svg>
                                            </span>
                                            {{ item.patente || 'Sin patente' }}
                                        </div>
                    <div class="text-sm text-gray-500">
                      {{ item.remito_proveedor || 'Sin remito' }} â€¢ {{ item.chofer }}
                    </div>
                </div>
                <div class="text-right">
                                        <div class="font-bold flex items-center justify-end gap-1">
                                            <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                                <path d="M3 20h18" />
                                                <path d="M6 20V7a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v13" />
                                                <path d="M10 9h4" />
                                            </svg>
                                            {{ formatTn(item.produccion) }}
                                        </div>
                                        <div class="text-xs text-gray-400 flex items-center justify-end gap-1">
                                            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                                                <line x1="16" y1="2" x2="16" y2="6" />
                                                <line x1="8" y1="2" x2="8" y2="6" />
                                                <line x1="3" y1="10" x2="21" y2="10" />
                                            </svg>
                                            {{ formatDate(item.fecha) }}
                                        </div>
                </div>
            </div>
            <div v-if="item.remito_fgpy" class="text-xs text-gray-400 mt-2">Remito FGPY: {{ item.remito_fgpy }}</div>
            <div v-if="item.observaciones" class="text-xs text-gray-400 mt-1">{{ item.observaciones }}</div>
        </div>
    </div>
    <div v-else class="space-y-3">
        <div v-if="movimientosCarreton.length === 0" class="text-center text-sm text-gray-500">No hay movimientos de carretÃ³n en este rango.</div>
        <div v-for="item in movimientosCarreton" :key="item.id" class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow">
            <div class="flex justify-between items-start gap-3">
                <div>
                    <div class="font-bold">{{ item.patente || 'Sin mÃ³vil' }}</div>
                    <div class="text-sm text-gray-500">{{ item.unidad_negocio || 'Sin unidad' }} â€¢ {{ item.chofer }}</div>
                </div>
                <div class="text-right">
                    <div class="font-bold">{{ Number(item.km_inicial).toFixed(2) }} - {{ Number(item.km_final).toFixed(2) }}</div>
                    <div class="text-xs text-gray-400">{{ formatDate(item.fecha) }}</div>
                </div>
            </div>
            <div class="text-xs text-gray-400 mt-2">Estado: {{ item.estado_carga || 'Sin estado' }}</div>
            <div v-if="item.hora_inicio_viaje" class="text-xs text-gray-400 mt-1">Inicio viaje: {{ formatTime(item.hora_inicio_viaje) }}</div>
            <div v-if="item.tipo_maquina_transportada" class="text-xs text-gray-400 mt-1">MÃ¡quina: {{ item.tipo_maquina_transportada }}</div>
        </div>
    </div>
  </div>
</template>
