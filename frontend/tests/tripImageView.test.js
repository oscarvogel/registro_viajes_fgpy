import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')

test('router exposes authenticated standalone trip image view', async () => {
  const source = await read('../src/router/index.js')
  assert.ok(/import TripImageUpload from ['"]\.\.\/views\/TripImageUpload\.vue['"]/.test(source))
  assert.match(source, /path:\s*['"]\/new-trip\/image['"][\s\S]*?component:\s*TripImageUpload[\s\S]*?requiresAuth:\s*true/)
})

test('NewTrip keeps OCR entry separate and before carreton and manual form', async () => {
  const source = await read('../src/views/NewTrip.vue')
  const entry = source.indexOf('Cargar desde foto')
  const description = source.indexOf('Foto de remito y ticket de balanza')
  const imageRoute = source.indexOf("router.push('/new-trip/image')")
  const carreton = source.indexOf('carreton-move')
  const form = source.indexOf('<form')
  const submit = source.indexOf('Guardar Registro')
  assert.ok(entry > -1 && description > entry && imageRoute > description)
  assert.ok(imageRoute < carreton && carreton < form && form < submit)
  assert.doesNotMatch(source.slice(form), /Cargar desde foto|new-trip\/image/)
  const entrySection = source.lastIndexOf('<section', entry)
  assert.ok(entrySection > -1)
  assert.match(source.slice(entrySection, carreton), /border-(?:emerald|blue)-/)
})

test('TripImageUpload uses only approved OCR and catalog dependencies', async () => {
  const source = await read('../src/views/TripImageUpload.vue')
  for (const name of [
    'analyzeTripImage', 'confirmTripImage', 'fetchTripImageBlob',
    'createTripImageObjectUrl', 'revokeTripImageObjectUrl', 'mapTripImageError',
    'readTripImageSettings', 'createReviewModel', 'buildConfirmPayload', 'transitionReviewState',
    'useCatalogStore',
  ]) assert.match(source, new RegExp(`\\b${name}\\b`))
  assert.doesNotMatch(source, /stores\/sync|from ['"]\.\.\/db|saveRecord|IndexedDB|offline queue/i)
})

test('TripImageUpload renders selecting, processing, reviewing, success and safe error controls', async () => {
  const source = await read('../src/views/TripImageUpload.vue')
  assert.match(source, /type="file"[^>]*accept="image\/jpeg,image\/png,image\/webp"[^>]*capture="environment"/)
  for (const state of ['selecting', 'processing', 'reviewing', 'confirming', 'success', 'error']) {
    assert.match(source, new RegExp(`state\\s*={2,3}\\s*['"]${state}['"]`))
  }
  for (const field of ['fecha_remision', 'fecha_recepcion', 'numero_remision_fpv', 'proveedor_id', 'peso_bruto_destino', 'tara_destino', 'neto_destino', 'observaciones']) {
    assert.match(source, new RegExp(`review\\.${field}`))
  }
  assert.match(source, /Se toma de Ajustes/)
  assert.match(source, /warnings/)
  assert.match(source, /:disabled="[^\"]*(?:confirming|processing|busy)[^\"]*"/)
  assert.match(source, /router\.(?:push|replace)\(['"]\/settings['"]\)/)
  assert.match(source, /router\.(?:push|replace)\(['"]\/history['"]\)/)
})

test('TripImageUpload owns preview URLs and calls exact OCR actions', async () => {
  const source = await read('../src/views/TripImageUpload.vue')
  assert.match(source, /onMounted\([\s\S]*?fetchCatalogues/)
  assert.match(source, /onUnmounted\([\s\S]*?revokeTripImageObjectUrl/)
  assert.match(source, /createReviewModel\([\s\S]*?localToday\(\)/)
  assert.match(source, /await analyzeTripImage\(selectedFile\.value\)/)
  assert.match(source, /buildConfirmPayload\(review\.value, settings\.value\)/)
  assert.match(source, /await confirmTripImage\(payload\)/)
  assert.match(source, /await fetchTripImageBlob\(/)
  assert.match(source, /createTripImageObjectUrl\(/)
  assert.match(source, /revokeTripImageObjectUrl\(/)
  assert.doesNotMatch(source, /toISOString\(\)\.split\(['"]T['"]\)/)
  assert.doesNotMatch(source, /console\./)
})
