import { defineStore } from 'pinia';
import axios from 'axios';
import Swal from 'sweetalert2';
import { saveToStore, getAllFromStore, deleteFromStore } from '../db';
import { useCatalogStore } from './catalog';
import { API_URL } from '../config';
import { clientLogger } from '@/services/logger';
import { recoverBlockedCarretonKmRecord, syncOnePendingRecord } from '@/services/syncPendingRecord';
import { safeConsole } from '@/services/safeConsole';

export const useSyncStore = defineStore('sync', {
    state: () => ({
        pendingRecords: [],
        lastSyncSummary: null,
    }),
    actions: {
        async syncAll() {
            clientLogger.info('Iniciando sincronizacion completa', {
                event_type: 'sync',
                extra: { pending_count: this.pendingRecords.length }
            });

            const catalog = useCatalogStore();
            try {
                const counts = await catalog.fetchCatalogues();
                clientLogger.info('Catalogos sincronizados', {
                    event_type: 'sync',
                    extra: counts
                });
                this._lastCounts = counts || {};
            } catch (e) {
                clientLogger.error('Error sincronizando catalogos', {
                    event_type: 'sync',
                    error_name: e.name,
                    error_message: e.message
                });
            }

            await this.loadPending();
            const result = await this.syncPending();

            clientLogger.info('Sincronizacion completada', {
                event_type: 'sync',
                extra: result
            });

            return this._lastCounts || {};
        },
        async loadPending() {
            this.pendingRecords = await getAllFromStore('registros');
        },
        async saveRecord(record, recordType = 'viaje') {
            clientLogger.info('Guardando registro localmente', {
                event_type: 'data',
                extra: { type: recordType }
            });

            record.record_type = recordType;
            record.synced = false;
            record.timestamp = new Date().toISOString();

            await saveToStore('registros', JSON.parse(JSON.stringify(record)));
            await this.loadPending();

            return await this.syncPending();
        },
        async syncPending() {
            if (this.pendingRecords.length === 0) {
                this.lastSyncSummary = { synced: true, failed: 0, success: 0, blocked: 0, blockedRecords: [], authRequired: false };
                return this.lastSyncSummary;
            }

            clientLogger.info(`Sincronizando ${this.pendingRecords.length} registros pendientes`, {
                event_type: 'sync'
            });

            let failed = 0;
            let success = 0;
            let blocked = 0;
            let authRequired = false;
            const blockedRecords = [];

            for (const record of this.pendingRecords) {
                let recordToSync = record;

                if (record.blocked) {
                    const recoveredRecord = recoverBlockedCarretonKmRecord(record);

                    if (recoveredRecord) {
                        recordToSync = recoveredRecord;
                        await saveToStore('registros', JSON.parse(JSON.stringify(recoveredRecord)));

                        clientLogger.info('Registro de carreton bloqueado recuperado para reintento', {
                            event_type: 'sync',
                            extra: { local_id: record.local_id, type: record.record_type || 'carreton' }
                        });
                    } else {
                        failed += 1;
                        blocked += 1;
                        blockedRecords.push({
                            local_id: record.local_id,
                            type: record.record_type || 'viaje',
                            detail: record.blocked_reason || 'Registro bloqueado por validacion',
                        });
                        continue;
                    }
                }

                const syncResult = await syncOnePendingRecord({
                    record: recordToSync,
                    apiUrl: API_URL,
                    httpClient: axios,
                    clientLogger,
                });
                const recordType = syncResult.recordType || recordToSync.record_type || 'viaje';

                if (syncResult.ok) {
                    safeConsole.debug('Sync response:', syncResult.response.status);
                    await deleteFromStore('registros', recordToSync.local_id);
                    success += 1;

                    clientLogger.info('Registro sincronizado exitosamente', {
                        event_type: 'sync',
                        extra: { local_id: recordToSync.local_id, type: recordType }
                    });
                    continue;
                }

                if (syncResult.authRequired) {
                    failed += 1;
                    authRequired = true;
                    clientLogger.warning('Sincronizacion detenida por sesion expirada', {
                        event_type: 'sync',
                        extra: { local_id: recordToSync.local_id, type: recordType, status: syncResult.status }
                    });
                    break;
                }

                if (syncResult.blocked) {
                    const blockedRecord = {
                        ...recordToSync,
                        blocked: true,
                        blocked_reason: syncResult.detail || 'Registro bloqueado por validacion.',
                        blocked_at: new Date().toISOString(),
                    };
                    await saveToStore('registros', JSON.parse(JSON.stringify(blockedRecord)));

                    clientLogger.warning('Registro pendiente bloqueado', {
                        event_type: 'sync',
                        extra: {
                            local_id: recordToSync.local_id,
                            type: recordType,
                            status: syncResult.status,
                            blocked_reason: blockedRecord.blocked_reason,
                        }
                    });

                    failed += 1;
                    blocked += 1;
                    blockedRecords.push({ local_id: recordToSync.local_id, type: recordType, detail: blockedRecord.blocked_reason });
                    continue;
                }

                safeConsole.error('Sync failed for record', recordToSync.local_id, syncResult.error || syncResult.detail);
                clientLogger.error('Error sincronizando registro', {
                    event_type: 'sync',
                    error_name: syncResult.error?.name,
                    error_message: syncResult.error?.message || syncResult.detail,
                    extra: {
                        local_id: recordToSync.local_id,
                        type: recordType,
                        status: syncResult.status,
                        response_data: syncResult.error?.response?.data
                    }
                });

                failed += 1;
            }

            await this.loadPending();

            const result = { synced: failed === 0, failed, success, blocked, blockedRecords, authRequired };
            this.lastSyncSummary = result;

            if (failed > 0) {
                clientLogger.warning(`Sincronizacion completada con ${failed} errores`, {
                    event_type: 'sync',
                    extra: result
                });
            }

            if (authRequired) {
                await Swal.fire({
                    icon: 'warning',
                    title: 'Sesion expirada',
                    text: 'Debe iniciar sesion nuevamente para sincronizar los registros pendientes.',
                    confirmButtonColor: '#d97706'
                });
            } else if (blockedRecords.length > 0) {
                const firstBlocked = blockedRecords[0];
                await Swal.fire({
                    icon: 'warning',
                    title: 'Registro bloqueado',
                    text: firstBlocked.detail,
                    confirmButtonColor: '#d97706'
                });
            }

            return result;
        },
        async removePending(local_id) {
            clientLogger.info('Eliminando registro pendiente', { event_type: 'data', extra: { local_id } });
            try {
                await deleteFromStore('registros', local_id);
                await this.loadPending();
                return { removed: true };
            } catch (e) {
                clientLogger.error('Error eliminando registro pendiente', { event_type: 'data', error_message: e.message, extra: { local_id } });
                return { removed: false, error: e };
            }
        }
    }
});
