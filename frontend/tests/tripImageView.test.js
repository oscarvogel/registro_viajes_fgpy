import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import * as tripImage from '../src/services/tripImage.js'

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8')

test('trip image file validation accepts safe MIME or extension and rejects invalid input before preview', () => {
  const jpeg = new Blob(['jpeg'], { type: 'image/jpeg' })
  Object.defineProperty(jpeg, 'name', { value: 'capture.bin' })
  assert.equal(tripImage.validateTripImageFile(jpeg), jpeg)

  const cameraJpeg = new Blob(['jpeg'], { type: '' })
  Object.defineProperty(cameraJpeg, 'name', { value: 'CAMERA.JPG' })
  assert.equal(tripImage.validateTripImageFile(cameraJpeg), cameraJpeg)

  const unknown = new Blob(['raw'], { type: '' })
  Object.defineProperty(unknown, 'name', { value: 'camera.bin' })
  assert.throws(() => tripImage.validateTripImageFile(unknown), /JPG, PNG o WEBP/i)
  assert.throws(() => tripImage.validateTripImageFile(new Blob(['x'], { type: 'image/gif' })), /JPG, PNG o WEBP/i)
  assert.throws(() => tripImage.validateTripImageFile(new Blob([new Uint8Array((10 * 1024 * 1024) + 1)], { type: 'image/png' })), /10 MB/i)
})

test('trip image lifecycle prevents preview creation after unmount', () => {
  const lifecycle = tripImage.createTripImageLifecycle()
  let calls = 0
  assert.equal(lifecycle.runIfActive(() => { calls += 1; return 'created' }), 'created')
  lifecycle.deactivate()
  assert.equal(lifecycle.runIfActive(() => { calls += 1 }), undefined)
  assert.equal(calls, 1)
  assert.equal(lifecycle.active, false)
})

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
