<script setup>
import { ref, onMounted, computed } from 'vue';
import axios from 'axios';
import Swal from 'sweetalert2';
import { useCatalogStore } from '../stores/catalog';
import { API_URL } from '../config';
import Autocomplete from '../components/Autocomplete.vue';
import { buildFuelLastKmParams, buildFuelPayload, getLastFuelKmHora, getStoredUserId } from '../services/criticalScreens';

const catalog = useCatalogStore();

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

  console.log('ðŸš› FuelLoad mounted - PaÃ±oles disponibles:', catalog.panioles.length, catalog.panioles);

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
  if (!form.value.equipo_id) faltantes.push('CamiÃ³n');
  if (!form.value.paniol_id) faltantes.push('Tanque');
  if (!form.value.remito) faltantes.push('NÂº Remito');

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
      title: 'KM/Hora invÃ¡lido',
      text: `El KM/Hora debe ser mayor o igual a ${lastKmHora.value.toFixed(2)} (Ãºltimo registrado)`,
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
          label="CamiÃ³n"
          :items="camiones"
          v-model="form.equipo_id"
          :displayFn="(e) => `${e.patente} â€¢ ${e.descripcion}`"
          placeholder="Configurar en Ajustes"
          :disabled="true"
        />
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">KM/Hora del camiÃ³n</label>
        <input v-model.number="form.km_hora" type="number" step="0.01" :min="lastKmHora" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
        <div v-if="lastKmHora > 0" class="text-xs text-gray-500 mt-1">Ãšltimo registrado: {{ lastKmHora.toFixed(2) }}</div>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Tanque (PaÃ±ol)</label>
        <select v-model="form.paniol_id" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
          <option value="" disabled>Seleccione un tanque</option>
          <option v-for="p in catalog.panioles" :key="p.id" :value="p.id">
            {{ p.descripcion }}
          </option>
        </select>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">NÂº Remito</label>
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
