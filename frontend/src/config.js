const env = import.meta.env || {};

const API_BASE_URL = env.MODE === 'production'
  ? 'https://viajes.forestalparaguay.com/api'
  : env.VITE_API_URL || 'http://localhost:8000/api';

const APP_VERSION = env.VITE_APP_VERSION || 'dev';
const ADMIN_USER_IDS = (env.VITE_ADMIN_USER_IDS || '')
  .split(',')
  .map((id) => Number(id.trim()))
  .filter((id) => Number.isInteger(id));

// Mantener retrocompatibilidad
const API_URL = API_BASE_URL;

export { API_URL, API_BASE_URL, APP_VERSION, ADMIN_USER_IDS };
