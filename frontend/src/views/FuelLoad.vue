<script setup>
import { ref, onMounted, computed } from 'vue';
import axios from 'axios';
import { useRouter } from 'vue-router';
import Swal from 'sweetalert2';
import { useCatalogStore } from '../stores/catalog';
import { API_URL } from '../config';
import Autocomplete from '../components/Autocomplete.vue';
import { buildFuelLastKmParams, buildFuelPayload, getLastFuelKmHora, getStoredUserId } from '../services/criticalScreens';
import { FUEL_TIPO_REMITO_INTERNO, FUEL_TIPO_TICKET } from '../services/fuelImage';

const catalog = useCatalogStore();
const router = useRouter();

const openFuelImage = (tipo) => {
  router.push({ path: '/fuel-load/image', query: { tipo } });
};

const form = ref({
  fecha_carga: new Date().toISOString().split('T')[0],
  litros: 0,
  km_hora: 0,
  equipo_id: '',
  paniol_id: '',
  remito: '',
  observaciones: ''
});

const lastKmHora = ref(0);
const camiones = computed(() => catalog.equipos.filter(e => e.tipo_movil_id === 4));

const formatApiError = (error) => {
  const status = error?.response?.status;
  const data = error?.response?.data;
  const detail = data?.detail;

  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item;
        const field = Array.isArray(item?.loc) ? item.loc.join('.') : item?.loc;
        return field ? `${field}: ${item?.msg || 'Dato invalido'}` : (item?.msg || JSON.stringify(item));
      })
      .join('\n');
  }

  if (detail && typeof detail === 'object') {
    return JSON.stringify(detail);
  }

  if (data?.message) {
    return data.message;
  }

  if (!error?.response) {
    return 'No se pudo conectar con el servidor. Verifique la conexion e intente nuevamente.';
  }

  return status ? `El servidor rechazo la carga (HTTP ${status}).` : 'No se pudo registrar la carga.';
};

const fetchLastKmHora = async (equipoId) => {
  if (!equipoId) return;

  try {
    const response = await axios.get(`${API_URL}/movimientos-combustible`, {
      params: buildFuelLastKmParams({ equipoId })
    });

    const kmHora = getLastFuelKmHora(response.data);
    if (kmHora !== null) {
      lastKmHora.value = kmHora;
      // Save to localStorage
      localStorage.setItem(`last_km_hora_${equipoId}`, lastKmHora.value.toString());
      form.value.km_hora = lastKmHora.value;
    }
  } catch (e) {
    // Offline or error: try localStorage
    const stored = localStorage.getItem(`last_km_hora_${equipoId}`);
    if (stored) {
      lastKmHora.value = parseFloat(stored);
      form.value.km_hora = lastKmHora.value;
    }
  }
};

onMounted(async () => {
  await catalog.fetchCatalogues();

  console.log('🚛 FuelLoad mounted - Pañoles disponibles:', catalog.panioles.length, catalog.panioles);

  const defaultPatente = localStorage.getItem('default_patente');
  if (defaultPatente && !form.value.equipo_id) {
    const match = camiones.value.find(e => e.patente === defaultPatente);
    if (match) {
      form.value.equipo_id = match.id;
      await fetchLastKmHora(match.id);
    }
  }
});

const submitForm = async () => {
  const faltantes = [];
  if (!form.value.fecha_carga) faltantes.push('Fecha de carga');
  if (!form.value.litros || form.value.litros <= 0) faltantes.push('Litros cargados');
  if (!form.value.km_hora || form.value.km_hora <= 0) faltantes.push('KM/Hora');
  if (!form.value.equipo_id) faltantes.push('Camión');
  if (!form.value.paniol_id) faltantes.push('Tanque');
  if (!form.value.remito) faltantes.push('Nº Remito');

  if (faltantes.length > 0) {
    Swal.fire({
      icon: 'warning',
      title: 'Faltan datos obligatorios',
      html: `<div style="text-align: left;">Los siguientes campos son requeridos:<ul style="margin-top: 10px;">${faltantes.map(f => `<li>${f}</li>`).join('')}</ul></div>`,
      confirmButtonColor: '#007AFF'
    });
    return;
  }

  // Validate km_hora is not less than last registered
  if (form.value.km_hora < lastKmHora.value) {
    Swal.fire({
      icon: 'warning',
      title: 'KM/Hora inválido',
      text: `El KM/Hora debe ser mayor o igual a ${lastKmHora.value.toFixed(2)} (último registrado)`,
      confirmButtonColor: '#007AFF'
    });
    return;
  }

  const userId = getStoredUserId();

  try {
    await axios.post(`${API_URL}/movimiento-combustible`, buildFuelPayload({ form: form.value, userId }));

    // Update last km_hora after successful registration
    lastKmHora.value = form.value.km_hora;
    localStorage.setItem(`last_km_hora_${form.value.equipo_id}`, lastKmHora.value.toString());

    Swal.fire({
      icon: 'success',
      title: 'Guardado',
      text: 'Carga registrada correctamente',
      timer: 1500,
      showConfirmButton: false
    });

    form.value.litros = 0;
    form.value.remito = '';
    form.value.observaciones = '';
    // Keep km_hora at last value for next entry
  } catch (e) {
    const message = formatApiError(e);
    console.error('Error al registrar carga de combustible:', e?.response?.data || e);

    Swal.fire({
      icon: 'error',
      title: 'No se pudo guardar la carga',
      text: message,
      confirmButtonColor: '#007AFF'
    });
  }
};
</script>

<template>
  <div class="max-w-md mx-auto p-4 pb-20">
    <header class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-bold dark:text-white">Carga de Combustible</h1>
      <div class="text-xs px-2 py-1 rounded bg-green-100 text-green-800" v-if="!catalog.isOffline">Conectado</div>
      <div class="text-xs px-2 py-1 rounded bg-orange-100 text-orange-800" v-else>Offline</div>
    </header>

    <section class="bg-gradient-to-br from-amber-50 to-orange-50 dark:from-amber-950/40 dark:to-orange-950/40 p-4 rounded-xl shadow-sm mb-6 border border-amber-200 dark:border-amber-800/60">
      <div class="flex items-start gap-3">
        <div class="shrink-0 rounded-full bg-amber-600 p-2 text-white" aria-hidden="true">
          <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h1l2-3h8l2 3h1a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9zm9 8a4 4 0 100-8 4 4 0 000 8z" />
          </svg>
        </div>
        <div class="min-w-0 flex-1">
          <h2 class="text-lg font-semibold text-amber-950 dark:text-amber-100">Cargar desde foto</h2>
          <p class="mt-1 text-sm text-amber-800 dark:text-amber-200">Ticket INFONET o remito interno</p>
          <div class="mt-4 space-y-3">
            <button
              type="button"
              @click="openFuelImage(FUEL_TIPO_TICKET)"
              class="min-h-11 w-full rounded-lg bg-amber-600 px-4 py-2 font-medium text-white shadow hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-2"
            >
              📷 Cargar ticket de estación
            </button>
            <button
              type="button"
              @click="openFuelImage(FUEL_TIPO_REMITO_INTERNO)"
              class="min-h-11 w-full rounded-lg bg-amber-600 px-4 py-2 font-medium text-white shadow hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-2"
            >
              📋 Cargar remito interno
            </button>
          </div>
        </div>
      </div>
    </section>

    <form @submit.prevent="submitForm" class="space-y-4">
      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Fecha de carga</label>
        <input v-model="form.fecha_carga" type="date" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Litros cargados</label>
        <input v-model.number="form.litros" type="number" step="0.01" min="0" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
      </div>

      <div>
        <Autocomplete
          label="Camión"
          :items="camiones"
          v-model="form.equipo_id"
          :displayFn="(e) => `${e.patente} • ${e.descripcion}`"
          placeholder="Configurar en Ajustes"
          :disabled="true"
        />
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">KM/Hora del camión</label>
        <input v-model.number="form.km_hora" type="number" step="0.01" :min="lastKmHora" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
        <div v-if="lastKmHora > 0" class="text-xs text-gray-500 mt-1">Último registrado: {{ lastKmHora.toFixed(2) }}</div>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Tanque (Pañol)</label>
        <select v-model="form.paniol_id" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
          <option value="" disabled>Seleccione un tanque</option>
          <option v-for="p in catalog.panioles" :key="p.id" :value="p.id">
            {{ p.descripcion }}
          </option>
        </select>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Nº Remito</label>
        <input v-model="form.remito" type="text" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Observaciones</label>
        <textarea v-model="form.observaciones" rows="3" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white"></textarea>
      </div>

      <button type="submit" class="w-full bg-blue-600 text-white py-3 rounded-lg font-medium shadow-lg mt-4">
        Registrar carga
      </button>
    </form>
  </div>
</template>
