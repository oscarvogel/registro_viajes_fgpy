import { defineStore } from 'pinia';
import axios from 'axios';
import { saveToStore, getAllFromStore } from '../db';
import { API_URL } from '../config';

export const useCatalogStore = defineStore('catalog', {
    state: () => ({
        empleados: [],
            clientes: [],
        proveedores: [],
        equipos: [],
        panioles: [],
        unidadesNegocio: [],
        isOffline: false
    }),
    actions: {
        async fetchCatalogues() {
            try {
                // Try network
                // In parallel - request with high limit to get all records
                // Use allSettled to tolerate partial failures (e.g., /clientes may not exist)
                const requests = [
                    axios.get(`${API_URL}/empleados`, { params: { limit: 10000 } }),
                    axios.get(`${API_URL}/proveedores`, { params: { limit: 10000 } }),
                    axios.get(`${API_URL}/equipos`, { params: { limit: 10000 } }),
                    axios.get(`${API_URL}/panioles`, { params: { limit: 10000 } }),
                    axios.get(`${API_URL}/unidades-negocio`, { params: { limit: 10000 } }),
                    axios.get(`${API_URL}/clientes`, { params: { limit: 10000 } })
                ];

                const settled = await Promise.allSettled(requests);
                const results = settled.map(r => (r.status === 'fulfilled' ? r.value : null));
                const [empRes, provRes, eqRes, panRes, unRes, cliRes] = results;

                if (!cliRes) console.warn('Advertencia: /clientes no respondiÃ³ correctamente o devolviÃ³ error');

                console.log('ðŸ” Respuesta raw de paÃ±oles:', panRes);
                console.log('ðŸ” panRes.data:', panRes.data);
                console.log('ðŸ” Tipo de panRes.data:', typeof panRes.data, Array.isArray(panRes.data));

                this.empleados = Array.isArray(empRes.data) ? empRes.data : [];
                this.proveedores = Array.isArray(provRes.data) ? provRes.data : [];
                this.equipos = Array.isArray(eqRes.data) ? eqRes.data : [];
                this.panioles = Array.isArray(panRes.data) ? panRes.data : [];
                this.unidadesNegocio = Array.isArray(unRes.data) ? unRes.data : [];
                this.clientes = cliRes && Array.isArray(cliRes.data) ? cliRes.data : [];

                console.log('ðŸ“¦ CatÃ¡logos obtenidos:', {
                    empleados: this.empleados.length,
                    proveedores: this.proveedores.length,
                    equipos: this.equipos.length,
                    panioles: this.panioles.length,
                    unidadesNegocio: this.unidadesNegocio.length
                });

                // Verificar si todos los paÃ±oles tienen id
                const paniolesInvalidos = this.panioles.filter(p => !p.id);
                if (paniolesInvalidos.length > 0) {
                    console.error('âŒ PaÃ±oles sin ID:', paniolesInvalidos.length, paniolesInvalidos.slice(0, 5));
                }

                console.log('ðŸ” Primeros 3 paÃ±oles:', this.panioles.slice(0, 3));

                // Update IDB - Clone deep to remove Vue proxy observers
                await saveToStore('empleados', JSON.parse(JSON.stringify(this.empleados)));
                await saveToStore('proveedores', JSON.parse(JSON.stringify(this.proveedores)));
                await saveToStore('equipos', JSON.parse(JSON.stringify(this.equipos)));
                await saveToStore('clientes', JSON.parse(JSON.stringify(this.clientes)));
                // Filter out invalid panioles before saving
                const validPanioles = this.panioles.filter(p => p && p.id);
                console.log('ðŸ’¾ Guardando paÃ±oles vÃ¡lidos:', validPanioles.length, 'de', this.panioles.length);
                await saveToStore('panioles', JSON.parse(JSON.stringify(validPanioles)));
                await saveToStore('unidadesNegocio', JSON.parse(JSON.stringify(this.unidadesNegocio)));

                console.log('ðŸ’¾ CatÃ¡logos guardados en IndexedDB');

                this.isOffline = false;

                // Return counts for callers
                return {
                    empleados: this.empleados.length,
                    proveedores: this.proveedores.length,
                    equipos: this.equipos.length,
                    panioles: this.panioles.length,
                    unidadesNegocio: this.unidadesNegocio.length
                };

            } catch (error) {
                console.log("Network failed, loading from IDB", error);
                this.isOffline = true;
                this.empleados = (await getAllFromStore('empleados')) || [];
                this.proveedores = (await getAllFromStore('proveedores')) || [];
                this.clientes = (await getAllFromStore('clientes')) || [];
                this.equipos = (await getAllFromStore('equipos')) || [];
                this.panioles = (await getAllFromStore('panioles')) || [];
                this.unidadesNegocio = (await getAllFromStore('unidadesNegocio')) || [];

                console.log('ðŸ“± CatÃ¡logos cargados desde IndexedDB (offline):', {
                    empleados: this.empleados.length,
                    proveedores: this.proveedores.length,
                    equipos: this.equipos.length,
                    panioles: this.panioles.length,
                    unidadesNegocio: this.unidadesNegocio.length
                });

                return {
                    empleados: this.empleados.length,
                    proveedores: this.proveedores.length,
                    equipos: this.equipos.length,
                    panioles: this.panioles.length,
                    unidadesNegocio: this.unidadesNegocio.length,
                    offline: true
                };
            }
        }
    }
});
