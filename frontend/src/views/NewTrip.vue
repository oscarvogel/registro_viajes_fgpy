<script setup>
import { ref, onMounted, computed, watch } from 'vue';
import axios from 'axios';
import { useRouter } from 'vue-router';
import { useCatalogStore } from '../stores/catalog';
import { useSyncStore } from '../stores/sync';
import Autocomplete from '../components/Autocomplete.vue';
import Swal from 'sweetalert2';
import { API_URL } from '../config';
import { safeConsole } from '../services/safeConsole';
import {
    findEquipoByPatente,
    buildViajePayload,
    combineRemito,
    getPendingViajeLastLectura,
    getUnidadLecturaLabel,
    normalizarLectura,
    toUnidadLecturaLabel,
    LECTURA_STORAGE_PREFIX
} from '../services/criticalScreens.js';

const router = useRouter();
const catalog = useCatalogStore();
const sync = useSyncStore();

// Interruptor de obligatoriedad de la lectura. Lo define el admin en
// GET /api/app-version; por defecto la lectura es obligatoria.
const exigirLecturaCamion = ref(true);
const ultimaLectura = ref(null);
const cargandoUltimaLectura = ref(false);

const form = ref({
    fecha_remision: new Date().toISOString().split('T')[0],
    fecha_recepcion: new Date().toISOString().split('T')[0],
    proveedor_id: '',
    cliente_id: '',
    remito_prov_tipo: '',
    remito_prov_sucursal: '',
    remito_prov_numero: '',
    remito_fpv_tipo: '',
    remito_fpv_sucursal: '',
    remito_fpv_numero: '',
    lote: '',
    peso_bruto_destino: 0,
    tara_destino: 0,
    neto_destino: 0,
    neto_origen: 0,
    chofer_id: '',
    patente: '',
    lectura_camion: '',
    unidad_negocio_id: 1,
    observaciones: ''
});

// La unidad la define el admin por camion (equipos.unidad_hr_km) y llega en el
// catalogo de equipos. Solo se usa para etiquetar el campo: el cliente nunca
// manda la unidad, la resuelve el servidor.
const unidadLecturaLabel = computed(() => getUnidadLecturaLabel(findEquipoByPatente(catalog.equipos, form.value.patente)));

const applyUltimaLectura = (value) => {
    if (value === null || value === undefined) {
        ultimaLectura.value = null;
        return;
    }
    const lectura = normalizarLectura(value.lectura_camion);
    if (!Number.isFinite(lectura) || lectura <= 0) {
        ultimaLectura.value = null;
        return;
    }
    ultimaLectura.value = {
        lectura: lectura,
        unidad: value.unidad_lectura ? toUnidadLecturaLabel(value.unidad_lectura) : unidadLecturaLabel.value,
        fecha: value.fecha || null
    };
};

const fetchUltimaLectura = async (equipoId) => {
    if (!equipoId) {
        ultimaLectura.value = null;
        return;
    }

    const storageKey = `${LECTURA_STORAGE_PREFIX}${equipoId}`;

    // Si hay viajes pendientes de este camion, la ultima lectura es la del
    // pendiente mas reciente (puede ser mas nueva que la del servidor).
    const pendingLectura = getPendingViajeLastLectura(sync.pendingRecords, form.value.patente);
    if (pendingLectura !== null) {
        applyUltimaLectura({ lectura_camion: pendingLectura });
        return;
    }

    cargandoUltimaLectura.value = true;
    try {
        const response = await axios.get(`${API_URL}/registro-viaje/ultima-lectura`, {
            params: { equipo_id: Number(equipoId) }
        });
        applyUltimaLectura(response.data);
        if (response.data && response.data.lectura_camion !== null && response.data.lectura_camion !== undefined) {
            try {
                localStorage.setItem(storageKey, String(response.data.lectura_camion));
            } catch (e) {
                // Sin localStorage disponible se sigue igual
            }
        }
    } catch (error) {
        // El endpoint puede no existir todavia (o no hay red): se usa el valor
        // cacheado en el dispositivo para que el formulario no se rompa.
        let cached = null;
        try {
            cached = localStorage.getItem(storageKey);
        } catch (e) {
            cached = null;
        }
        if (cached !== null && cached !== '') {
            applyUltimaLectura({ lectura_camion: cached });
        } else {
            ultimaLectura.value = null;
        }
    } finally {
        cargandoUltimaLectura.value = false;
    }
};

onMounted(async () => {
    await catalog.fetchCatalogues();

    // Interruptor de obligatoriedad de la lectura. Si no se puede consultar
    // (sin red o endpoint nuevo), se usa el valor cacheado en el dispositivo.
    try {
        const versionRes = await axios.get(`${API_URL}/app-version`);
        exigirLecturaCamion.value = versionRes.data?.exigir_lectura_camion !== false;
        try {
            localStorage.setItem('exigir_lectura_camion', String(exigirLecturaCamion.value));
        } catch (e) {
            // Sin localStorage disponible se sigue igual
        }
    } catch (error) {
        try {
            const cachedFlag = localStorage.getItem('exigir_lectura_camion');
            if (cachedFlag !== null) {
                exigirLecturaCamion.value = cachedFlag !== 'false';
            }
        } catch (e) {
            exigirLecturaCamion.value = true;
        }
    }

    // Auto-select logged in driver
    const userStr = localStorage.getItem('user');
    if (userStr) {
        const user = JSON.parse(userStr);
        const matchedEmp = catalog.empleados.find(e => e.id === user.id);
        if (matchedEmp) {
            form.value.chofer_id = matchedEmp.id;
        }
    }

    // Auto-select default Vehicle if set and field is empty
    const defaultPatente = localStorage.getItem('default_patente');
    if (defaultPatente && !form.value.patente) {
        form.value.patente = defaultPatente;
    }

    // Auto-select default Unidad de Negocio
    const defaultUnidadNegocio = localStorage.getItem('default_unidad_negocio');
    if (defaultUnidadNegocio) {
        form.value.unidad_negocio_id = parseInt(defaultUnidadNegocio);
    }

    // Los viajes pendientes locales son la referencia mas reciente cuando hay
    // viajes todavia no sincronizados de este camion.
    try {
        await sync.loadPending();
    } catch (e) {
        // Sin pendientes no hay ultima lectura local que consultar
    }

    const equipo = findEquipoByPatente(catalog.equipos, form.value.patente);
    if (equipo) {
        await fetchUltimaLectura(equipo.id);
    }
});

const calculatedNet = computed(() => {
    const net = (form.value.peso_bruto_destino - form.value.tara_destino);
    form.value.neto_destino = parseFloat(net.toFixed(2));
    return net.toFixed(2);
});

const selectedUnidad = computed(() => {
    return catalog.unidadesNegocio.find(u => u.id === form.value.unidad_negocio_id) || null;
});

const isTC = computed(() => {
    const u = selectedUnidad.value;
    if (!u || !u.descripcion) return false;
    const desc = String(u.descripcion).toLowerCase();
    return desc.includes('transporte chip') || desc.includes('(tc)') || desc.includes('tc');
});

// Clear cliente/proveedor when switching business unit type
watch(isTC, (newIsTC, oldIsTC) => {
    if (oldIsTC !== undefined && newIsTC !== oldIsTC) {
        form.value.cliente_id = '';
        form.value.proveedor_id = '';
    }
});

const padZeros = (value, length) => {
    return String(value || '').padStart(length, '0');
};

const onRemitoPadTipo = (field) => {
    form.value[field] = padZeros(form.value[field], 3);
};

const onRemitoPadSucursal = (field) => {
    form.value[field] = padZeros(form.value[field], 3);
};

const onRemitoPadNumero = (field) => {
    form.value[field] = padZeros(form.value[field], 7);
};

const remitoPattern = /^\d{3}-\d{3}-\d{7}$/;

const submitForm = async () => {
    // Basic validation
    const needProveedor = !isTC.value;
    const needCliente = isTC.value;

    if ((needProveedor && !form.value.proveedor_id) || (needCliente && !form.value.cliente_id) || !form.value.chofer_id || !form.value.patente || !form.value.neto_origen || !form.value.neto_destino) {
        Swal.fire({
            icon: 'warning',
            title: 'Faltan datos',
            text: 'Complete los campos obligatorios',
            confirmButtonColor: '#007AFF'
        });
        return;
    }

    // Lectura del tablero: el operador puede escribirla con coma decimal
    // (1234,5) porque el campo no es un input numerico.
    const lecturaValor = normalizarLectura(form.value.lectura_camion);
    const lecturaValida = Number.isFinite(lecturaValor) && lecturaValor > 0;

    if (exigirLecturaCamion.value && !lecturaValida) {
        Swal.fire({
            icon: 'warning',
            title: 'Faltan datos',
            text: 'Complete la lectura de km/horas del camion',
            confirmButtonColor: '#007AFF'
        });
        return;
    }

    // La lectura es acumulada: si es menor a la anterior del mismo camion se
    // avisa y el chofer confirma con "Guardar igual".
    let permitirLecturaMenor = false;
    if (lecturaValida && ultimaLectura.value && lecturaValor < ultimaLectura.value.lectura) {
        const confirmacion = await Swal.fire({
            icon: 'warning',
            title: 'Lectura menor que la anterior',
            html: `La lectura (${lecturaValor}) es menor a la ultima registrada (${ultimaLectura.value.lectura}).<br>¿Desea continuar y guardar el registro igual?`,
            showCancelButton: true,
            confirmButtonText: 'Guardar igual',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#d97706'
        });
        if (!confirmacion.isConfirmed) {
            return;
        }
        // El chofer confirmo con "Guardar igual": el payload viaja con
        // permitir_lectura_menor = true para que el backend lo acepte.
        permitirLecturaMenor = true;
    }

    // Combinar campos de remito
    const numero_remision = combineRemito(
        form.value.remito_prov_tipo,
        form.value.remito_prov_sucursal,
        form.value.remito_prov_numero
    );

    const numero_remision_fpv = combineRemito(
        form.value.remito_fpv_tipo,
        form.value.remito_fpv_sucursal,
        form.value.remito_fpv_numero
    );

    // Validate remito formats if provided
    if (numero_remision && !remitoPattern.test(numero_remision)) {
        Swal.fire({
            icon: 'warning',
            title: 'Formato inválido',
            text: 'El Nº Remito Proveedor debe tener formato 000-000-0000000',
            confirmButtonColor: '#007AFF'
        });
        return;
    }
    if (numero_remision_fpv && !remitoPattern.test(numero_remision_fpv)) {
        Swal.fire({
            icon: 'warning',
            title: 'Formato inválido',
            text: 'El Nº Remito FGPY debe tener formato 000-000-0000000',
            confirmButtonColor: '#007AFF'
        });
        return;
    }

    try {
        await sync.loadPending();

        const localDuplicate = sync.pendingRecords.some(r =>
            (r.record_type || 'viaje') === 'viaje' && (
                (numero_remision && r.numero_remision === numero_remision) ||
                (numero_remision_fpv && r.numero_remision_fpv === numero_remision_fpv)
            )
        );

        if (localDuplicate) {
            Swal.fire({
                icon: 'warning',
                title: 'Remito duplicado',
                text: 'Ese número de remito ya está registrado (pendiente).',
                confirmButtonColor: '#007AFF'
            });
            return;
        }

        try {
            const existsRes = await axios.get(`${API_URL}/remitos/existe`, {
                params: {
                    numero_remision: numero_remision,
                    numero_remision_fpv: numero_remision_fpv
                }
            });

            if (existsRes.data?.exists) {
                const msg = existsRes.data.exists_proveedor
                    ? 'El Nº Remito Proveedor ya existe.'
                    : 'El Nº Remito FGPY ya existe.';
                Swal.fire({
                    icon: 'warning',
                    title: 'Remito duplicado',
                    text: msg,
                    confirmButtonColor: '#007AFF'
                });
                return;
            }
        } catch (e) {
            // If offline or error, allow local save; backend will validate on sync
        }

        const result = await sync.saveRecord(buildViajePayload({
            form: form.value,
            userId: form.value.chofer_id,
            lecturaCamion: lecturaValor,
            permitirLecturaMenor: permitirLecturaMenor
        }), 'viaje');
        if (lecturaValida) {
            // La lectura recien guardada pasa a ser la referencia para el
            // proximo registro de esta pantalla.
            ultimaLectura.value = {
                lectura: lecturaValor,
                unidad: unidadLecturaLabel.value,
                fecha: new Date().toISOString().split('T')[0]
            };
        }
        if (result?.synced) {
            Swal.fire({
                icon: 'success',
                title: 'Guardado',
                text: 'Registro guardado exitosamente',
                timer: 1500,
                showConfirmButton: false
            });
        } else {
            Swal.fire({
                icon: 'warning',
                title: 'Pendiente de sincronización',
                text: 'El registro quedó guardado localmente y se enviará cuando haya conexión.',
                confirmButtonColor: '#007AFF'
            });
        }
        // Reset form
        form.value.remito_prov_tipo = '';
        form.value.remito_prov_sucursal = '';
        form.value.remito_prov_numero = '';
        form.value.remito_fpv_tipo = '';
        form.value.remito_fpv_sucursal = '';
        form.value.remito_fpv_numero = '';
        form.value.peso_bruto_destino = 0;
        form.value.tara_destino = 0;
        form.value.neto_origen = 0;
        form.value.neto_destino = 0;
        // Keep dates and others?
    } catch (e) {
        safeConsole.error('Error guardando viaje:', e?.response?.status || e?.message);
        Swal.fire({
            icon: 'error',
            title: 'Error',
            text: 'Hubo un error al guardar el registro',
            confirmButtonColor: '#007AFF'
        });
    }
};

</script>

<template>
  <div class="max-w-md mx-auto p-4 pb-20">
    <header class="flex items-center justify-between mb-6">
        <h1 class="text-xl font-bold dark:text-white">Nuevo Registro</h1>
        <div class="text-xs px-2 py-1 rounded bg-green-100 text-green-800" v-if="!catalog.isOffline">Conectado</div>
        <div class="text-xs px-2 py-1 rounded bg-orange-100 text-orange-800" v-else>Offline</div>
    </header>

    <section class="bg-gradient-to-br from-emerald-50 to-blue-50 dark:from-emerald-950/40 dark:to-blue-950/40 p-4 rounded-xl shadow-sm mb-6 border border-emerald-200 dark:border-emerald-800/60">
        <div class="flex items-start gap-3">
            <div class="shrink-0 rounded-full bg-emerald-600 p-2 text-white" aria-hidden="true">
                <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h1l2-3h8l2 3h1a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9zm9 8a4 4 0 100-8 4 4 0 000 8z" />
                </svg>
            </div>
            <div class="min-w-0 flex-1">
                <h2 class="text-lg font-semibold text-emerald-950 dark:text-emerald-100">Cargar desde foto</h2>
                <p class="mt-1 text-sm text-emerald-800 dark:text-emerald-200">Foto de remito y ticket de balanza</p>
                <button type="button" @click="router.push('/new-trip/image')" class="mt-4 min-h-11 w-full rounded-lg bg-emerald-600 px-4 py-2 font-medium text-white shadow hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2">
                    Abrir cámara o elegir imagen
                </button>
            </div>
        </div>
    </section>

    <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow mb-6 border border-amber-100 dark:border-amber-900/40">
        <div class="flex items-start justify-between gap-4">
            <div>
                <div class="text-sm text-gray-500">Acceso rápido</div>
                <div class="text-lg font-semibold mt-1">Movimiento de carretón</div>
                <div class="text-sm text-gray-500 mt-1">Registrar móvil, KM inicial/final, estado y máquina transportada.</div>
            </div>
            <button @click="router.push('/carreton-move')" class="shrink-0 bg-amber-600 hover:bg-amber-700 text-white px-4 py-2 rounded-lg font-medium">
                Abrir
            </button>
        </div>
    </div>

    <form @submit.prevent="submitForm" class="space-y-4">
        <div class="grid grid-cols-2 gap-4">
            <div>
                <label class="block text-xs font-medium text-gray-500 mb-1">Fecha Remisión Prov.</label>
                <input v-model="form.fecha_remision" type="date" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
            </div>
            <div>
                <label class="block text-xs font-medium text-gray-500 mb-1">Fecha Recepción</label>
                <input v-model="form.fecha_recepcion" type="date" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
            </div>
        </div>

        <div>
            <!-- Conditionally show Cliente or Proveedor -->
            <template v-if="isTC">
                <Autocomplete
                    label="Cliente"
                    :items="catalog.clientes"
                    v-model="form.cliente_id"
                    :displayFn="(p) => p.razon_social"
                    placeholder="Buscar cliente..."
                />
            </template>
            <template v-else>
                <Autocomplete
                    label="Proveedor"
                    :items="catalog.proveedores"
                    v-model="form.proveedor_id"
                    :displayFn="(p) => p.razon_social"
                    placeholder="Buscar proveedor..."
                />
            </template>
        </div>

        <div>
            <label class="block text-xs font-medium text-gray-500 mb-1">Nº Remito Proveedor</label>
            <div class="grid grid-cols-3 gap-2">
                <input
                    v-model="form.remito_prov_tipo"
                    type="text"
                    inputmode="numeric"
                    maxlength="3"
                    placeholder="002"
                    @blur="onRemitoPadTipo('remito_prov_tipo')"
                    class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white text-center">
                <input
                    v-model="form.remito_prov_sucursal"
                    type="text"
                    inputmode="numeric"
                    maxlength="3"
                    placeholder="001"
                    @blur="onRemitoPadSucursal('remito_prov_sucursal')"
                    class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white text-center">
                <input
                    v-model="form.remito_prov_numero"
                    type="text"
                    inputmode="numeric"
                    maxlength="7"
                    placeholder="0008880"
                    @blur="onRemitoPadNumero('remito_prov_numero')"
                    class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white text-center">
            </div>
            <div class="text-xs text-gray-400 mt-1">Tipo - Sucursal - Número</div>
        </div>
        <div>
            <label class="block text-xs font-medium text-gray-500 mb-1">Nº Remito FGPY (Interno)</label>
            <div class="grid grid-cols-3 gap-2">
                <input
                    v-model="form.remito_fpv_tipo"
                    type="text"
                    inputmode="numeric"
                    maxlength="3"
                    placeholder="002"
                    @blur="onRemitoPadTipo('remito_fpv_tipo')"
                    class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white text-center">
                <input
                    v-model="form.remito_fpv_sucursal"
                    type="text"
                    inputmode="numeric"
                    maxlength="3"
                    placeholder="001"
                    @blur="onRemitoPadSucursal('remito_fpv_sucursal')"
                    class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white text-center">
                <input
                    v-model="form.remito_fpv_numero"
                    type="text"
                    inputmode="numeric"
                    maxlength="7"
                    placeholder="0008880"
                    @blur="onRemitoPadNumero('remito_fpv_numero')"
                    class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white text-center">
            </div>
            <div class="text-xs text-gray-400 mt-1">Tipo - Sucursal - Número</div>
        </div>

        <div class="grid grid-cols-2 gap-4">
             <div>
                <label class="block text-xs font-medium text-gray-500 mb-1">Peso Bruto Destino (Tn)</label>
                <input v-model.number="form.peso_bruto_destino" type="number" step="0.01" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
            </div>
            <div>
                <label class="block text-xs font-medium text-gray-500 mb-1">Tara Destino (Tn)</label>
                <input v-model.number="form.tara_destino" type="number" step="0.01" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white">
            </div>
        </div>

        <div>
            <label class="block text-xs font-medium text-gray-500 mb-1">Neto Destino (Tn)</label>
            <input v-model.number="form.neto_destino" type="number" step="0.01" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white" placeholder="Calculado automáticamente">
        </div>
        <div></div>
        <div class="text-xs text-gray-400 -mt-2">Neto Destino precalculado: {{ calculatedNet }} Tn</div>

        <div>
            <label class="block text-xs font-medium text-gray-500 mb-1">Neto Origen (Tn) <span class="text-red-500">*</span></label>
            <input v-model.number="form.neto_origen" required type="number" step="0.01" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white" placeholder="Solicitar al final">
        </div>

        <!-- Autocomplete for Chofer -->
        <Autocomplete
            label="Chofer"
            :items="catalog.empleados"
            v-model="form.chofer_id"
            :displayFn="(c) => `${c.apellido} ${c.nombre}`"
            placeholder="Chofer logueado"
            :disabled="true"
        />

        <div>
            <label class="block text-xs font-medium text-gray-500 mb-1">Patente</label>
            <input v-model="form.patente" type="text" class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white uppercase" disabled>
            <div class="text-xs text-gray-400 mt-1">Se configura desde Ajustes</div>
        </div>

        <div>
            <label class="block text-xs font-medium text-gray-500 mb-1">
                Lectura del camion ({{ unidadLecturaLabel }}) <span v-if="exigirLecturaCamion" class="text-red-500">*</span>
            </label>
            <input
                v-model="form.lectura_camion"
                type="text"
                inputmode="decimal"
                autocomplete="off"
                class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white"
                placeholder="Lectura actual del tablero">
            <div v-if="cargandoUltimaLectura" class="text-xs text-gray-400 mt-1">Buscando ultima lectura...</div>
            <div v-else-if="ultimaLectura" class="text-xs text-gray-400 mt-1">
                Ultima lectura: {{ ultimaLectura.lectura.toFixed(2) }} {{ ultimaLectura.unidad }}
            </div>
            <div v-else class="text-xs text-gray-400 mt-1">Aun no hay lecturas registradas para este camion.</div>
        </div>

        <button type="submit" class="w-full bg-blue-600 text-white py-3 rounded-lg font-medium shadow-lg mt-4">
            Guardar Registro
        </button>
    </form>
  </div>
</template>
