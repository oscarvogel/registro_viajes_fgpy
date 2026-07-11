const INDEX_FINGERPRINT_KEY = 'app_index_fingerprint';
const SW_FINGERPRINT_KEY = 'app_sw_fingerprint';

function hashString(value) {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = ((hash << 5) - hash) + value.charCodeAt(i);
    hash |= 0;
  }
  return String(hash);
}

function buildBypassUrl(path) {
  const separator = path.includes('?') ? '&' : '?';
  return `${path}${separator}__vcheck=${Date.now()}`;
}

async function fetchTextFingerprint(path) {
  try {
    const response = await fetch(buildBypassUrl(path), {
      method: 'GET',
      cache: 'no-store',
      headers: {
        'Cache-Control': 'no-cache'
      }
    });

    if (!response.ok) return null;

    const text = await response.text();
    if (!text) return null;

    return hashString(text);
  } catch (e) {
    return null;
  }
}

async function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function activateWaitingWorker(registration) {
  if (!registration || !registration.waiting) return false;

  try {
    registration.waiting.postMessage({ type: 'SKIP_WAITING' });
    return true;
  } catch (e) {
    return false;
  }
}

export async function updateServiceWorkerAndDetectIndexChange(registration) {
  if (!registration || typeof registration.update !== 'function') {
    return { updated: false, changed: false, activated: false };
  }

  const beforeIndex = await fetchTextFingerprint('/index.html');
  const beforeSw = await fetchTextFingerprint('/sw.js');

  const lastKnownIndex = localStorage.getItem(INDEX_FINGERPRINT_KEY);
  const lastKnownSw = localStorage.getItem(SW_FINGERPRINT_KEY);

  const baselineIndex = beforeIndex || lastKnownIndex;
  const baselineSw = beforeSw || lastKnownSw;

  if (beforeIndex) localStorage.setItem(INDEX_FINGERPRINT_KEY, beforeIndex);
  if (beforeSw) localStorage.setItem(SW_FINGERPRINT_KEY, beforeSw);

  await registration.update();
  await wait(300);
  await registration.update();

  const activated = await activateWaitingWorker(registration);

  const afterIndex = await fetchTextFingerprint('/index.html');
  const afterSw = await fetchTextFingerprint('/sw.js');

  if (afterIndex) localStorage.setItem(INDEX_FINGERPRINT_KEY, afterIndex);
  if (afterSw) localStorage.setItem(SW_FINGERPRINT_KEY, afterSw);

  const indexChanged = Boolean(afterIndex && baselineIndex && afterIndex !== baselineIndex);
  const swChanged = Boolean(afterSw && baselineSw && afterSw !== baselineSw);

  const changed = indexChanged || swChanged;

  // If SW changed but index hash is still same due propagation delays, treat it as change.

  return {
    updated: true,
    changed,
    activated,
    beforeIndex,
    afterIndex,
    beforeSw,
    afterSw,
  };
}
