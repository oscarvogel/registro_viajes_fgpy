import { openDB } from 'idb';

const DB_NAME = 'registro_viajes_db';
const DB_VERSION = 4;

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
        // Local records not yet synced.
        // We might want to use a separate store for synced history if we want to show it offline.
        db.createObjectStore('registros', { keyPath: 'local_id', autoIncrement: true });
    }
  },
});

export async function saveToStore(storeName, data) {
    const db = await dbPromise;
    const tx = db.transaction(storeName, 'readwrite');
    const store = tx.objectStore(storeName);
    // If data is array, put all
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
