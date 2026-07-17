# Alerta OCR Excepcional Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar la revisión OCR duplicada y mostrar una alerta compacta únicamente cuando chofer o patente observados difieran de la configuración efectiva.

**Architecture:** `tripImageReview.js` seguirá construyendo el modelo editable, pero separará las advertencias generales del proveedor de una lista explícita `configurationWarnings`. `TripImageUpload.vue` renderizará solamente esa lista excepcional; la tarjeta de configuración y el payload de confirmación no cambian.

**Tech Stack:** Vue 3, JavaScript ES modules, Node test runner, Vitest, Vue Test Utils, Tailwind CSS, Vite/PWA.

---

### Task 1: Separar discrepancias útiles en el modelo de revisión

**Files:**
- Modify: `frontend/src/services/tripImageReview.js:99-136`
- Test: `frontend/tests/tripImage.test.js:145-177`

- [ ] **Step 1: Reemplazar las expectativas actuales por pruebas que fallen**

Actualizar el test de `createReviewModel` para exigir que las advertencias del proveedor no aparezcan como discrepancias y que las diferencias sean concretas:

```javascript
test('createReviewModel exposes only concrete configuration mismatches', () => {
  const review = createReviewModel(analysis, settings, '2026-07-13')

  assert.deepEqual(review.warnings, ['borroso'])
  assert.deepEqual(review.configurationWarnings, [
    'La foto parece indicar ZZ999ZZ; en Ajustes figura AB 123 CD.',
    'La foto parece indicar Otra Persona; el usuario actual es Pérez Ana.',
  ])
})

test('createReviewModel omits configuration warnings when OCR matches or is absent', () => {
  for (const observed of ['Ana Pérez', 'Pérez Ana', null]) {
    const review = createReviewModel({
      ...analysis,
      proposal: {
        ...analysis.proposal,
        patente_observada: observed ? 'AB123CD' : null,
        chofer_observado: observed,
      },
    }, settings, '2026-07-13')
    assert.deepEqual(review.configurationWarnings, [])
  }
})
```

- [ ] **Step 2: Ejecutar la prueba y comprobar el rojo**

Run: `cd frontend && node --test tests/tripImage.test.js`

Expected: FAIL porque `configurationWarnings` todavía no existe y las discrepancias siguen mezcladas en `warnings`.

- [ ] **Step 3: Implementar la lista excepcional**

En `createReviewModel`, conservar las advertencias crudas únicamente como dato interno y construir mensajes concretos separados:

```javascript
const warnings = [...list(proposal.warnings)]
const configurationWarnings = []
const observedPlate = observedValue(proposal, 'patente_observada', 'observed_plate', 'patente')
const observedDriver = observedValue(proposal, 'chofer_observado', 'observed_driver', 'chofer')

if (observedPlate && normalizedText(observedPlate) !== normalizedText(settings?.patente)) {
  configurationWarnings.push(
    `La foto parece indicar ${observedPlate}; en Ajustes figura ${settings?.patente || 'sin configurar'}.`,
  )
}

const userName = settings?.user?.nombre || ''
const userSurname = settings?.user?.apellido || ''
const configuredDriver = `${userSurname} ${userName}`.trim()
const configuredDrivers = [
  normalizedText(`${userName} ${userSurname}`),
  normalizedText(`${userSurname} ${userName}`),
]
if (observedDriver && !configuredDrivers.includes(normalizedText(observedDriver))) {
  configurationWarnings.push(
    `La foto parece indicar ${observedDriver}; el usuario actual es ${configuredDriver || 'desconocido'}.`,
  )
}
```

Agregar `configurationWarnings` al objeto retornado sin modificar `config`, `observed`, `warnings` ni los campos de confirmación.

- [ ] **Step 4: Ejecutar la prueba focal y comprobar el verde**

Run: `cd frontend && node --test tests/tripImage.test.js`

Expected: todos los tests de `tripImage.test.js` PASS.

- [ ] **Step 5: Commit del modelo**

```bash
git add frontend/src/services/tripImageReview.js frontend/tests/tripImage.test.js
git commit -m "fix: separar discrepancias OCR de advertencias generales"
```

### Task 2: Sustituir el bloque duplicado por la alerta compacta

**Files:**
- Modify: `frontend/src/views/TripImageUpload.vue:231-237`
- Modify: `frontend/tests/tripImageUpload.spec.js`

- [ ] **Step 1: Agregar pruebas de componente que fallen**

Crear dos casos montando la vista. El primero usa el análisis base sin discrepancias:

```javascript
it('does not render an OCR warning block when configuration matches', async () => {
  const wrapper = await mountView()
  await selectFile(wrapper, file())

  expect(wrapper.text()).not.toContain('Datos observados en la foto')
  expect(wrapper.text()).not.toContain('Revisá la configuración')
})
```

El segundo modifica el resultado OCR:

```javascript
it('renders one compact alert only for concrete configuration mismatches', async () => {
  mocks.analyze.mockResolvedValueOnce({
    ...analysis,
    proposal: {
      ...analysis.proposal,
      warnings: ['Texto general que no debe mostrarse'],
      patente_observada: 'ZZ999ZZ',
      chofer_observado: 'Otra Persona',
    },
  })
  const wrapper = await mountView()
  await selectFile(wrapper, file())

  const alert = wrapper.get('[role="alert"]')
  expect(alert.text()).toContain('Revisá la configuración')
  expect(alert.text()).toContain('La foto parece indicar ZZ999ZZ; en Ajustes figura AB 123 CD.')
  expect(alert.text()).toContain('La foto parece indicar Otra Persona; el usuario actual es Pérez Ana.')
  expect(alert.text()).not.toContain('Texto general que no debe mostrarse')
  expect(wrapper.text()).not.toContain('Datos observados en la foto')
})
```

- [ ] **Step 2: Ejecutar Vitest y comprobar el rojo**

Run: `cd frontend && npx vitest run tests/tripImageUpload.spec.js`

Expected: FAIL porque el template todavía muestra `Datos observados en la foto` y las advertencias generales.

- [ ] **Step 3: Reemplazar el bloque del template**

Sustituir la sección amarilla actual por:

```vue
<section
  v-if="review.configurationWarnings.length"
  class="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100"
  role="alert"
>
  <h2 class="font-semibold">Revisá la configuración</h2>
  <ul class="mt-2 list-disc space-y-1 pl-5">
    <li v-for="warning in review.configurationWarnings" :key="warning">{{ warning }}</li>
  </ul>
</section>
```

No renderizar `review.warnings`, `review.observed.patente` ni `review.observed.chofer` en ninguna otra parte de la vista.

- [ ] **Step 4: Ejecutar las pruebas del componente**

Run: `cd frontend && npx vitest run tests/tripImageUpload.spec.js`

Expected: todos los tests PASS, incluidos los casos sin alerta y con discrepancias.

- [ ] **Step 5: Commit de la interfaz**

```bash
git add frontend/src/views/TripImageUpload.vue frontend/tests/tripImageUpload.spec.js
git commit -m "fix: mostrar solo alertas OCR excepcionales"
```

### Task 3: Verificación integral y despliegue frontend

**Files:**
- No source changes expected.

- [ ] **Step 1: Ejecutar el gate frontend completo**

Run: `cd frontend && npm ci && npm run verify`

Expected: 79 pruebas Node, 6 pruebas Vitest y build Vite/PWA PASS; `verify-built-css.mjs` termina con código 0.

- [ ] **Step 2: Verificar que no cambió el contrato de confirmación**

Run: `cd frontend && node --test tests/tripImage.test.js --test-name-pattern="buildConfirmPayload"`

Expected: tests de payload PASS y siguen tomando chofer/patente/unidad desde `settings`.

- [ ] **Step 3: Inspeccionar el diff final**

Run: `git status -sb && git diff ca6eb5f...HEAD --check && git diff ca6eb5f...HEAD --stat`

Expected: únicamente especificación, plan, modelo/test y vista/test del ajuste; los directorios locales `.codegraph`, `.cursor` y `.superpowers` permanecen sin seguimiento.

- [ ] **Step 4: Verificar visualmente en móvil**

Levantar el frontend local, ingresar al flujo OCR y comprobar:

1. análisis sin discrepancias: no hay bloque amarillo;
2. análisis con discrepancia: una sola alerta compacta;
3. tarjeta `Configuración del viaje`: una sola aparición de chofer, patente y unidad;
4. CSS y modo oscuro conservados.

- [ ] **Step 5: Desplegar sólo el artefacto frontend**

En `fasa_195`, crear un backup fechado de `/var/www/html/django/viajes_fgpy/frontend`, copiar el nuevo `frontend/dist` de forma atómica y verificar por Nginx:

```bash
test -s /var/www/html/django/viajes_fgpy/frontend/index.html
grep -q '/new-trip/image' /var/www/html/django/viajes_fgpy/frontend/assets/*.js
! grep -E '@tailwind|@apply' /var/www/html/django/viajes_fgpy/frontend/assets/*.css
systemctl is-active viajes.service
```

Expected: frontend nuevo servido, ruta presente, CSS procesado y `viajes.service` continúa `active`; no se ejecuta migración ni reinicio.

- [ ] **Step 6: Actualizar el issue #12**

Agregar comentario con commits, pruebas, captura/resultado visual y evidencia de producción. Mantener el issue abierto hasta verificar una confirmación real desde un dispositivo configurado.
