import { openDB } from 'idb';

const DB_NAME = 'registro_viajes_db';
const DB_VERSION = 5;

export const OFFLINE_OPERATIONS_STORE = 'offlineOperations';

export const dbPromise = openDB(DB_NAME, DB_VERSION, {
  upgrade(db) {
    if (!db.objectStoreNames.contains('empleados')) {
        db.createObjectStore('empleados', { keyPath: 'id' });
    }
    if (!db.objectStoreNames.contains('proveedores')) {
        db.createObjectStore('proveedores', { keyPath: 'id' });
    }
    if (!db.objectStoreNames.contains('equipos')) {
        db.createObjectStore('equipos', { keyPath: 'id' });
    }
    if (!db.objectStoreNames.contains('panioles')) {
        db.createObjectStore('panioles', { keyPath: 'id' });
    }
    if (!db.objectStoreNames.contains('unidadesNegocio')) {
        db.createObjectStore('unidadesNegocio', { keyPath: 'id' });
    }
    if (!db.objectStoreNames.contains('clientes')) {
        db.createObjectStore('clientes', { keyPath: 'id' });
    }
    if (!db.objectStoreNames.contains('registros')) {
        // Legacy local queue. Keep it intact while the generic offline queue is rolled out.
        db.createObjectStore('registros', { keyPath: 'local_id', autoIncrement: true });
    }
    if (!db.objectStoreNames.contains(OFFLINE_OPERATIONS_STORE)) {
        const store = db.createObjectStore(OFFLINE_OPERATIONS_STORE, { keyPath: 'client_uuid' });
        store.createIndex('by_status', 'status');
        store.createIndex('by_entity_type', 'entity_type');
        store.createIndex('by_created_at_local', 'created_at_local');
    }
  },
});

export async function saveToStore(storeName, data) {
    const db = await dbPromise;
    const tx = db.transaction(storeName, 'readwrite');
    const store = tx.objectStore(storeName);
    if (Array.isArray(data)) {
        await Promise.all(data.map(item => store.put(item)));
    } else {
        await store.put(data);
    }
    await tx.done;
}

export async function getAllFromStore(storeName) {
    const db = await dbPromise;
    return db.getAll(storeName);
}

export async function deleteFromStore(storeName, key) {
    const db = await dbPromise;
    return db.delete(storeName, key);
}
