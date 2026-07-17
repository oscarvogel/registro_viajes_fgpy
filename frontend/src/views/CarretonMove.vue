<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import axios from 'axios';
import Swal from 'sweetalert2';
import Autocomplete from '../components/Autocomplete.vue';
import { useCatalogStore } from '../stores/catalog';
import { useSyncStore } from '../stores/sync';
import { API_URL } from '../config';
import {
  buildCarretonPayload,
  findEquipoByPatente,
  findUnidadById,
  getPendingCarretonLastKm,
  getStoredUserId,
  normalizePatente
} from '../services/criticalScreens';

const catalog = useCatalogStore();
const syncStore = useSyncStore();

const form = ref({
  fecha: new Date().toISOString().split('T')[0],
  equipo_id: '',
  unidad_negocio_id: '',
  hora_inicio_viaje: '',
  km_inicial: '',
  km_final: '',
  estado_carga: 'vacío',
  tipo_maquina_transportada: '',
  origen_carreton: '',
  destino_carreton: '',
});

const saving = ref(false);
const loadingLastKm = ref(false);
const lastKmFinal = ref(null);
const moviles = computed(() => catalog.equipos.filter(e => e.tipo_movil_id === 4));

const applyDefaultsFromSettings = () => {
  const defaultPatente = localStorage.getItem('default_patente');
  if (defaultPatente && !form.value.equipo_id) {
    const equipo = findEquipoByPatente(moviles.value, defaultPatente);
    if (equipo) {
      form.value.equipo_id = equipo.id;
    }
  }

  const defaultUnidadNegocio = localStorage.getItem('default_unidad_negocio');
  if (defaultUnidadNegocio && !form.value.unidad_negocio_id) {
    const unidad = findUnidadById(catalog.unidadesNegocio, defaultUnidadNegocio);
    if (unidad) {
      form.value.unidad_negocio_id = unidad.id;
    }
  }
};

const getPendingLastKm = (equipoId) => {
  return getPendingCarretonLastKm(syncStore.pendingRecords, equipoId);
};

const applyLastKm = (value) => {
  if (value === null || Number.isNaN(Number(value))) {
    lastKmFinal.value = null;
    return;
  }

  lastKmFinal.value = Number(value);
  form.value.km_inicial = Number(value);
};

const fetchLastKm = async (equipoId) => {
  if (!equipoId) {
    lastKmFinal.value = null;
    form.value.km_inicial = '';
    return;
  }

  const pendingKm = getPendingLastKm(equipoId);
  if (pendingKm !== null) {
    applyLastKm(pendingKm);
    return;
  }

  const storedKm = localStorage.getItem(`last_km_carreton_${equipoId}`);

  loadingLastKm.value = true;
  try {
    const response = await axios.get(`${API_URL}/movimientos-carreton/ultimo`, {
      params: { equipo_id: Number(equipoId) }
    });

    if (response.data && response.data.km_final !== undefined && response.data.km_final !== null) {
      const kmFinal = Number(response.data.km_final);
      localStorage.setItem(`last_km_carreton_${equipoId}`, kmFinal.toString());
      applyLastKm(kmFinal);
    } else if (storedKm !== null) {
      applyLastKm(Number(storedKm));
    } else {
      lastKmFinal.value = null;
      form.value.km_inicial = '';
    }
  } catch (error) {
    if (storedKm !== null) {
      applyLastKm(Number(storedKm));
    } else {
      lastKmFinal.value = null;
      form.value.km_inicial = '';
    }
  } finally {
    loadingLastKm.value = false;
  }
};

onMounted(async () => {
  await catalog.fetchCatalogues();
  await syncStore.loadPending();

  applyDefaultsFromSettings();
  if (form.value.equipo_id) {
    await fetchLastKm(form.value.equipo_id);
  }
});

watch([moviles, () => catalog.unidadesNegocio], () => {
  applyDefaultsFromSettings();
}, { deep: true });

watch(() => form.value.equipo_id, async (equipoId, previousEquipoId) => {
  if (!equipoId) {
    lastKmFinal.value = null;
    form.value.km_inicial = '';
    return;
  }

  if (equipoId !== previousEquipoId) {
    form.value.km_final = '';
    await fetchLastKm(equipoId);
  }
});

const submitForm = async () => {
  const faltantes = [];

  if (!form.value.equipo_id) faltantes.push('Móvil');
  if (!form.value.unidad_negocio_id) faltantes.push('Unidad de negocio');
  if (form.value.km_inicial === '' || Number.isNaN(Number(form.value.km_inicial))) faltantes.push('KM inicial');
  if (form.value.km_final === '' || Number.isNaN(Number(form.value.km_final))) faltantes.push('KM final');
  if (!form.value.estado_carga) faltantes.push('Vacío o cargado');
  if (!form.value.tipo_maquina_transportada.trim()) faltantes.push('Tipo de máquina transportada');

  if (faltantes.length > 0) {
    await Swal.fire({
      icon: 'warning',
      title: 'Faltan datos obligatorios',
      html: `<div style="text-align:left;">Complete los siguientes campos:<ul style="margin-top:10px;">${faltantes.map(item => `<li>${item}</li>`).join('')}</ul></div>`,
      confirmButtonColor: '#d97706'
    });
    return;
  }

  if (Number(form.value.km_inicial) < 0 || Number(form.value.km_final) < 0) {
    await Swal.fire({
      icon: 'warning',
      title: 'KM inválidos',
      text: 'Los kilómetros no pueden ser negativos.',
      confirmButtonColor: '#d97706'
    });
    return;
  }

  if (lastKmFinal.value !== null && Number(form.value.km_inicial) < Number(lastKmFinal.value)) {
    const confirmResult = await Swal.fire({
      icon: 'warning',
      title: 'KM inicial menor que el último registrado',
      html: `El KM inicial es menor al último KM final registrado (${Number(lastKmFinal.value).toFixed(2)}).<br>¿Desea continuar y guardar el registro igual?`,
      showCancelButton: true,
      confirmButtonText: 'Guardar igual',
      cancelButtonText: 'Cancelar',
      confirmButtonColor: '#d97706'
    });

    if (!confirmResult.isConfirmed) {
      return;
    }
  }

  if (Number(form.value.km_final) <= Number(form.value.km_inicial)) {
    await Swal.fire({
      icon: 'warning',
      title: 'KM inválidos',
      text: 'El KM final debe ser mayor al KM inicial.',
      confirmButtonColor: '#d97706'
    });
    return;
  }

  const userId = getStoredUserId();
  if (!userId) {
    await Swal.fire({
      icon: 'warning',
      title: 'Usuario no autenticado',
      text: 'Debe iniciar sesión antes de registrar movimientos.',
      confirmButtonColor: '#d97706'
    });
    saving.value = false;
    return;
  }

  saving.value = true;
  try {
    const result = await syncStore.saveRecord(buildCarretonPayload({ form: form.value, userId }), 'carreton');

    await Swal.fire({
      icon: result?.synced ? 'success' : (result?.blocked ? 'error' : 'warning'),
      title: result?.synced ? 'Guardado' : (result?.blocked ? 'Registro bloqueado' : 'Pendiente de sincronización'),
      text: result?.synced
        ? 'Movimiento de carretón registrado correctamente.'
        : (result?.blockedRecords?.[0]?.detail || 'El movimiento quedó guardado localmente y se enviará cuando haya conexión.'),
      timer: result?.synced ? 1500 : undefined,
      showConfirmButton: !result?.synced,
    });

    // Only update last KM if record was synced to server. If it remained pending, keep previous lastKM
    if (result?.synced) {
      localStorage.setItem(`last_km_carreton_${form.value.equipo_id}`, Number(form.value.km_final).toString());
      lastKmFinal.value = Number(form.value.km_final);
    }

    form.value.km_inicial = Number(form.value.km_final);
    form.value.km_final = '';
    form.value.hora_inicio_viaje = '';
    form.value.estado_carga = 'vacío';
    form.value.tipo_maquina_transportada = '';
    form.value.origen_carreton = '';
    form.value.destino_carreton = '';
  } catch (e) {
    const detail = e?.response?.data?.detail;
    const message = typeof detail === 'string' ? detail : 'No se pudo registrar el movimiento de carretón.';

    await Swal.fire({
      icon: 'error',
      title: 'Error',
      text: message,
      confirmButtonColor: '#d97706'
    });
  } finally {
    saving.value = false;
  }
};
</script>

<template>
  <div class="max-w-md mx-auto p-4 pb-20">
    <header class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-bold dark:text-white">Movimiento de carretón</h1>
      <div class="text-xs px-2 py-1 rounded bg-green-100 text-green-800" v-if="!catalog.isOffline">Conectado</div>
      <div class="text-xs px-2 py-1 rounded bg-orange-100 text-orange-800" v-else>Offline</div>
    </header>

    <form @submit.prevent="submitForm" class="space-y-4">
      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Fecha</label>
        <input v-model="form.fecha" type="date" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
      </div>

      <div>
        <Autocomplete
          label="Móvil"
          :items="moviles"
          v-model="form.equipo_id"
          :displayFn="(item) => `${item.patente} • ${item.descripcion}`"
          placeholder="Seleccione un móvil"
        />
        <div class="text-xs text-gray-400 mt-1">Se toma por defecto desde Ajustes, pero se puede cambiar.</div>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Unidad de negocio</label>
        <select v-model="form.unidad_negocio_id" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
          <option value="" disabled>Seleccione una unidad</option>
          <option v-for="unidad in catalog.unidadesNegocio" :key="unidad.id" :value="unidad.id">
            {{ unidad.descripcion }}<span v-if="unidad.prefijo"> ({{ unidad.prefijo }})</span>
          </option>
        </select>
        <div class="text-xs text-gray-400 mt-1">Se toma por defecto desde Ajustes, pero se puede cambiar.</div>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Hora inicio viaje (opcional)</label>
        <input v-model="form.hora_inicio_viaje" type="time" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
      </div>

      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-xs font-medium text-gray-500 mb-1">KM inicial</label>
          <input v-model.number="form.km_inicial" type="number" step="0.01" :min="0" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
          <div v-if="loadingLastKm" class="text-xs text-gray-400 mt-1">Buscando último kilometraje...</div>
          <div v-else-if="lastKmFinal !== null" class="text-xs text-gray-400 mt-1">Último KM final registrado: {{ Number(lastKmFinal).toFixed(2) }}</div>
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-500 mb-1">KM final</label>
          <input v-model.number="form.km_final" type="number" step="0.01" :min="form.km_inicial !== '' ? Number(form.km_inicial) + 0.01 : 0" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
        </div>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Vacío o cargado</label>
        <select v-model="form.estado_carga" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
          <option value="vacío">Vacío</option>
          <option value="cargado">Cargado</option>
        </select>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Tipo de máquina transportada</label>
        <input v-model="form.tipo_maquina_transportada" type="text" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white" placeholder="Ej: Excavadora, skidder, topadora">
        <div class="text-xs text-gray-400 mt-1">Se guarda en observaciones dentro de `tablero_produccion`.</div>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Origen del carretón</label>
        <input v-model="form.origen_carreton" type="text" maxlength="100" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white" placeholder="Dirección o lugar de origen">
        <div class="text-xs text-gray-400 mt-1">Máx. 100 caracteres.</div>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Destino del carretón</label>
        <input v-model="form.destino_carreton" type="text" maxlength="100" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white" placeholder="Dirección o lugar de destino">
        <div class="text-xs text-gray-400 mt-1">Máx. 100 caracteres.</div>
      </div>

      <button :disabled="saving" type="submit" class="w-full bg-amber-600 hover:bg-amber-700 disabled:bg-amber-300 text-white py-3 rounded-lg font-medium shadow-lg mt-4">
        <span v-if="!saving">Registrar movimiento</span>
        <span v-else>Guardando...</span>
      </button>
    </form>
  </div>
</template>
