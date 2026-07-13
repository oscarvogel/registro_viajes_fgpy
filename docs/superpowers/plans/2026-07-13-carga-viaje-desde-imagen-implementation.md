# Carga de viaje desde imagen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Incorporar una carga OCR confirmada por el operador que registra un viaje de pesaje único, conserva su imagen durante 60 días y no altera el flujo manual existente.

**Architecture:** Vue abre una ruta independiente para capturar, analizar y revisar la imagen. FastAPI mantiene la clave de MiniMax en el servidor, normaliza la extracción, consume un token temporal una sola vez y delega la creación del viaje a un servicio compartido; SQLAlchemy persiste `pesaje_unico` y la evidencia en una tabla separada.

**Tech Stack:** Vue 3, Pinia, Axios, Vite, Tailwind CSS 3/PostCSS, FastAPI, Pydantic 2, SQLAlchemy, MySQL/SQLite de pruebas, MiniMax Coding Plan MCP mediante `uvx`, `unittest` y Node test runner.

---

## Estructura de archivos

### Nuevos

- `backend/trip_image_normalization.py`: normalización determinista de remitos, fechas, pesos y nombres.
- `backend/minimax_vision.py`: adaptador acotado al proceso MCP de MiniMax; no contiene reglas de negocio.
- `backend/image_storage.py`: temporales, tokens firmados, promoción, lectura y eliminación de archivos.
- `backend/trip_service.py`: validación y creación compartida de viajes normales y de pesaje único.
- `backend/trip_image_service.py`: orquesta análisis, proveedor, confirmación y evidencia.
- `backend/migrations/20260713_add_trip_image_ocr.sql`: migración MySQL idempotente y explícita.
- `backend/migrations/20260713_verify_trip_image_ocr.sql`: consultas de verificación posteriores.
- `backend/test_trip_image_normalization.py`: pruebas puras de OCR y unidades.
- `backend/test_minimax_vision.py`: pruebas del protocolo MCP sin consumir MiniMax real.
- `backend/test_image_storage.py`: seguridad, tokens y retención.
- `backend/test_trip_image_api.py`: pruebas API/transacción con SQLite y MiniMax simulado.
- `frontend/postcss.config.js` y `frontend/tailwind.config.js`: pipeline CSS faltante.
- `frontend/scripts/verify-built-css.mjs`: impide publicar CSS con directivas sin procesar.
- `frontend/src/services/tripImage.js`: contrato HTTP del flujo OCR.
- `frontend/src/services/tripImageReview.js`: estado inicial, configuración móvil y payload de confirmación.
- `frontend/src/views/TripImageUpload.vue`: captura, procesamiento, revisión y confirmación.
- `frontend/tests/tripImage.test.js`: pruebas de contrato y reglas de la revisión.

### Modificados

- `backend/models.py`: `pesaje_unico`, nulabilidad de cliente y modelo `ViajeImagen`.
- `backend/schemas.py`: contratos de análisis, propuesta y confirmación.
- `backend/main.py`: endpoints delgados y uso de `trip_service` en el endpoint manual.
- `backend/scheduler.py`: job idempotente de limpieza.
- `backend/requirements.txt`: cliente HTTP/MCP sólo si el adaptador lo requiere; mantener dependencias mínimas.
- `frontend/package.json`: verificador CSS dentro de `build`/`verify`.
- `frontend/src/router/index.js`: ruta autenticada `/new-trip/image`.
- `frontend/src/views/NewTrip.vue`: botón OCR independiente antes del formulario manual.
- `README.md`: variables, migración, prueba real controlada y despliegue.

## Restricciones que atraviesan todas las tareas

- No imprimir ni comprometer `MINIMAX_API_KEY`.
- No guardar un viaje durante el análisis.
- El OCR no decide chofer, patente ni unidad de negocio.
- El backend fuerza `chofer_id=current_user.id` en la confirmación OCR.
- `cliente_id` queda `NULL`; no se sustituye por `1`.
- Para `pesaje_unico=true`: origen `0`, producción igual a neto destino.
- El flujo OCR requiere conexión; no entra en la cola offline de IndexedDB.
- Cada commit agrega sólo los archivos de su tarea y preserva `.codegraph/`, `.cursor/` y `.superpowers/` sin seguimiento.

---

### Task 1: Reparar y blindar el pipeline Tailwind/PostCSS

**Files:**
- Create: `frontend/postcss.config.js`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/scripts/verify-built-css.mjs`
- Modify: `frontend/package.json`
- Test: `frontend/scripts/verify-built-css.mjs`

- [ ] **Step 1: Escribir el verificador que debe fallar con CSS sin procesar**

Crear un script que recorra `dist/assets/*.css`, falle si no hay CSS y rechace `@tailwind` o `@apply`:

```javascript
import { readdir, readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const assets = resolve('dist/assets')
const cssFiles = (await readdir(assets)).filter((name) => name.endsWith('.css'))
if (cssFiles.length === 0) throw new Error('No se genero CSS en dist/assets')
for (const name of cssFiles) {
  const css = await readFile(resolve(assets, name), 'utf8')
  if (/@tailwind\b|@apply\b/.test(css)) throw new Error(`${name} contiene Tailwind sin procesar`)
  if (!css.includes('.fg-btn-primary')) throw new Error(`${name} no contiene componentes FGPY`)
}
```

- [ ] **Step 2: Ejecutar el build actual y demostrar el defecto**

Run: `cd frontend; npm run build; node scripts/verify-built-css.mjs`

Expected: FAIL indicando `@tailwind`, `@apply` o ausencia de `.fg-btn-primary`.

- [ ] **Step 3: Agregar configuración mínima de Tailwind 3**

```javascript
// postcss.config.js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } }
```

```javascript
// tailwind.config.js
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: { extend: {} },
  plugins: [],
}
```

Cambiar `build` para ejecutar el verificador después de Vite.

- [ ] **Step 4: Verificar pruebas y CSS compilado**

Run: `cd frontend; npm run test; npm run build`

Expected: todas las pruebas PASS, build con exit code `0`, CSS sin `@tailwind`/`@apply`.

- [ ] **Step 5: Commit**

```powershell
git add frontend/postcss.config.js frontend/tailwind.config.js frontend/scripts/verify-built-css.mjs frontend/package.json
git commit -m "fix: restaurar compilacion de estilos Tailwind"
```

---

### Task 2: Definir persistencia y migración explícita

**Files:**
- Modify: `backend/models.py`
- Create: `backend/migrations/20260713_add_trip_image_ocr.sql`
- Create: `backend/migrations/20260713_verify_trip_image_ocr.sql`
- Test: `backend/test_trip_image_api.py`

- [ ] **Step 1: Escribir una prueba de metadatos que falle**

```python
def test_modelo_declara_pesaje_unico_cliente_nullable_y_evidencia(self):
    tablero = self.models.TableroProduccion.__table__
    self.assertIn("pesaje_unico", tablero.columns)
    self.assertTrue(tablero.columns.cliente_id.nullable)
    evidencia = self.models.ViajeImagen.__table__
    self.assertTrue(evidencia.columns.token_hash.unique)
    self.assertIn("expires_at", evidencia.columns)
```

- [ ] **Step 2: Ejecutar la prueba y verificar el fallo**

Run: `py -m unittest backend.test_trip_image_api.TripImageApiTest.test_modelo_declara_pesaje_unico_cliente_nullable_y_evidencia -v`

Expected: FAIL porque las columnas/modelo aún no existen.

- [ ] **Step 3: Implementar el modelo**

Agregar `pesaje_unico = Column(Boolean, nullable=False, default=False)` y volver nullable `cliente_id`. Crear `ViajeImagen` con FK a `tablero_produccion`, `storage_path`, `original_name`, `mime_type`, `sha256`, `token_hash` único, `created_at`, `expires_at` y relación al viaje.

- [ ] **Step 4: Escribir migración MySQL idempotente y verificador**

La migración debe consultar `information_schema` antes de cada `ALTER`, conservar el tipo real de `cliente_id`, agregar índice por `expires_at` y FK de evidencia. El verificador debe devolver tipo/nulabilidad, existencia de tabla, índices y FK sin modificar datos.

- [ ] **Step 5: Verificar en SQLite y revisar SQL sin aplicarlo a producción**

Run: `py -m unittest backend.test_trip_image_api.TripImageApiTest.test_modelo_declara_pesaje_unico_cliente_nullable_y_evidencia -v`

Expected: PASS. Revisar: `rg -n "pesaje_unico|cliente_id|viaje_imagenes|expires_at" backend/migrations/20260713_*.sql`.

- [ ] **Step 6: Commit**

```powershell
git add backend/models.py backend/migrations backend/test_trip_image_api.py
git commit -m "feat: modelar pesaje unico y evidencia de imagen"
```

---

### Task 3: Normalizar extracción y conversiones sin IA

**Files:**
- Create: `backend/trip_image_normalization.py`
- Create: `backend/test_trip_image_normalization.py`

- [ ] **Step 1: Escribir pruebas fallidas para el documento de muestra**

```python
class TripImageNormalizationTest(unittest.TestCase):
    def test_normaliza_documento_de_muestra(self):
        result = normalize_extraction({
            "fecha_remision": "13/07/2026",
            "remito_tipo": "2", "remito_sucursal": "3", "remito_numero": "3677",
            "peso_bruto": "49.690", "tara": "17.080", "neto": "32.610",
            "unidad_peso": "kg", "proveedor_candidato": "ALCOGREEN S.A.",
        })
        self.assertEqual(result.fecha_remision.isoformat(), "2026-07-13")
        self.assertEqual(result.numero_remision_fpv, "002-003-0003677")
        self.assertEqual(result.peso_bruto_destino, Decimal("49.690"))
        self.assertEqual(result.tara_destino, Decimal("17.080"))
        self.assertEqual(result.neto_destino, Decimal("32.610"))
```

Agregar casos para coma decimal, puntos de miles, bruto menos tara fuera de tolerancia, prefijos faltantes y unidad distinta de kg.

- [ ] **Step 2: Verificar que las pruebas fallen**

Run: `py -m unittest backend.test_trip_image_normalization -v`

Expected: FAIL por módulo inexistente.

- [ ] **Step 3: Implementar normalización determinista**

Usar `Decimal`, una tolerancia de `0.010 TN`, remito `000-000-0000000`, fecha ISO o `DD/MM/YYYY`, y una función de nombre que quite acentos, puntuación y sufijos societarios sólo para comparar.

- [ ] **Step 4: Ejecutar pruebas**

Run: `py -m unittest backend.test_trip_image_normalization -v`

Expected: todos los casos PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/trip_image_normalization.py backend/test_trip_image_normalization.py
git commit -m "feat: normalizar datos OCR de viajes"
```

---

### Task 4: Encapsular MiniMax Vision y validar su contrato

**Files:**
- Create: `backend/minimax_vision.py`
- Create: `backend/test_minimax_vision.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Escribir pruebas con ejecutor MCP falso**

```python
def test_extrae_json_de_understand_image(self):
    executor = FakeMcpExecutor(result={"content": [{"type": "text", "text": VALID_JSON}]})
    client = MiniMaxVisionClient(api_key="secret", executor=executor)
    result = client.analyze(Path("sample.jpg"))
    self.assertEqual(result["remito_numero"], "3677")
    self.assertNotIn("secret", repr(executor.calls))

def test_rechaza_respuesta_no_json(self):
    with self.assertRaises(VisionResponseError):
        MiniMaxVisionClient("secret", FakeMcpExecutor(text="sin json")).analyze(Path("x.jpg"))
```

- [ ] **Step 2: Verificar el fallo**

Run: `py -m unittest backend.test_minimax_vision -v`

Expected: FAIL por módulo inexistente.

- [ ] **Step 3: Implementar el adaptador**

El adaptador debe ejecutar el comando configurable `MINIMAX_VISION_COMMAND` (default `uvx minimax-coding-plan-mcp -y`), enviar JSON-RPC `initialize` y `tools/call` para `understand_image`, pasar `MINIMAX_API_KEY` sólo mediante el entorno hijo, imponer timeout y tamaño máximo de salida, y parsear únicamente el JSON esperado. La plantilla debe exigir todos los campos del contrato y `null` para datos no visibles.

- [ ] **Step 4: Verificar pruebas sin red ni clave real**

Run: `py -m unittest backend.test_minimax_vision -v`

Expected: PASS y cero llamadas externas.

- [ ] **Step 5: Commit**

```powershell
git add backend/minimax_vision.py backend/test_minimax_vision.py backend/requirements.txt
git commit -m "feat: integrar MiniMax Vision mediante adaptador MCP"
```

---

### Task 5: Implementar almacenamiento temporal seguro y retención

**Files:**
- Create: `backend/image_storage.py`
- Create: `backend/test_image_storage.py`

- [ ] **Step 1: Escribir pruebas fallidas**

Cubrir JPEG/PNG/WebP por magic bytes, MIME falso, límite, nombre generado, token firmado con expiración, rechazo de traversal, promoción a ruta confirmada, repetición idempotente y eliminación por vencimiento.

```python
def test_token_expirado_no_abre_temporal(self):
    storage = ImageStorage(self.root, signing_key="test", now=lambda: EXPIRED_NOW)
    with self.assertRaises(ExpiredUploadToken):
        storage.resolve_temp(self.expired_token)
```

- [ ] **Step 2: Verificar el fallo**

Run: `py -m unittest backend.test_image_storage -v`

Expected: FAIL por módulo inexistente.

- [ ] **Step 3: Implementar almacenamiento**

Usar `VIAJE_IMAGE_STORAGE_DIR`, subdirectorios `tmp/YYYYMMDD` y `confirmed/YYYY/MM`, UUID de servidor, SHA-256, escritura exclusiva, tamaño `VIAJE_IMAGE_MAX_BYTES` default 10 MiB, token HMAC con `IMAGE_TOKEN_SECRET` y TTL temporal default 24 horas. Nunca aceptar una ruta desde el cliente.

- [ ] **Step 4: Ejecutar pruebas**

Run: `py -m unittest backend.test_image_storage -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/image_storage.py backend/test_image_storage.py
git commit -m "feat: almacenar imagenes de viaje de forma segura"
```

---

### Task 6: Extraer la creación de viajes y soportar `pesaje_unico`

**Files:**
- Create: `backend/trip_service.py`
- Modify: `backend/schemas.py`
- Modify: `backend/main.py:635-821`
- Modify: `backend/test_trip_image_api.py`

- [ ] **Step 1: Escribir pruebas de regresión y pesaje único**

```python
def test_pesaje_unico_guarda_origen_cero_y_produccion_destino(self):
    registro = make_registro(pesaje_unico=True, neto_origen=0, neto_destino=32.610,
                             peso_bruto_destino=49.690, tara_destino=17.080,
                             cliente_id=None)
    created = create_trip(self.db, registro, current_user=self.employee)
    self.assertEqual(Decimal(created.neto_origen), Decimal("0.00"))
    self.assertEqual(Decimal(created.produccion), Decimal("32.61"))
    self.assertIsNone(created.cliente_id)

def test_viaje_normal_sigue_rechazando_neto_origen_cero(self):
    with self.assertRaises(HTTPException):
        create_trip(self.db, make_registro(pesaje_unico=False, neto_origen=0), self.employee)
```

Agregar prueba que en confirmación OCR ignore un `chofer_id` ajeno y use `current_user.id`.

- [ ] **Step 2: Verificar fallos**

Run: `py -m unittest backend.test_trip_image_api -v`

Expected: FAIL por ausencia del servicio/campo.

- [ ] **Step 3: Implementar `trip_service.create_trip`**

Mover las validaciones de remito, equipo, proveedor, cliente, unidad, pesos y construcción de `TableroProduccion` desde `main.py`. Para modo único fijar origen a cero y producción desde destino; para modo normal conservar producción/origen actuales. Permitir que el llamador elija `commit=False` para que confirmación agregue evidencia en la misma transacción.

- [ ] **Step 4: Dejar el endpoint manual como adaptador delgado**

`create_registro_viaje` debe llamar al servicio con el contrato actual. No cambiar la UX ni convertirlo al flujo OCR. Añadir `pesaje_unico: bool = False` y `tara_destino` al esquema sin romper payloads existentes.

- [ ] **Step 5: Ejecutar regresión backend completa**

Run: `py -m unittest discover -s backend -p "test_*.py" -v`

Expected: todas las pruebas existentes y nuevas PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/trip_service.py backend/schemas.py backend/main.py backend/test_trip_image_api.py
git commit -m "feat: crear viajes con modalidad de pesaje unico"
```

---

### Task 7: Crear endpoints de análisis, confirmación e imagen

**Files:**
- Create: `backend/trip_image_service.py`
- Modify: `backend/schemas.py`
- Modify: `backend/main.py`
- Modify: `backend/test_trip_image_api.py`

- [ ] **Step 1: Escribir pruebas API/servicio fallidas**

Probar:

- `POST /api/registro-viaje/imagen/analizar` no crea `TableroProduccion`.
- Devuelve propuesta con Alcogreen único, remito y TN normalizadas.
- Proveedor ambiguo deja `proveedor_id=null` y advertencia.
- `POST /api/registro-viaje/imagen/confirmar` usa el usuario JWT, patente/unidad válidas y cliente null.
- Segunda confirmación devuelve el mismo viaje sin duplicarlo.
- Remito duplicado, token vencido y configuración inválida producen `400/409` claros.
- `GET /api/registro-viaje/imagenes/{id}` exige dueño o admin y entrega MIME correcto.

- [ ] **Step 2: Verificar fallos**

Run: `py -m unittest backend.test_trip_image_api -v`

Expected: FAIL porque los endpoints no existen.

- [ ] **Step 3: Implementar contratos Pydantic**

Definir `TripImageProposal`, `TripImageAnalysisResponse` y `TripImageConfirmRequest`. El request de confirmación contiene token, fecha, remito FGPY, proveedor, patente, unidad, bruto/tara/neto destino y observaciones; no acepta un chofer efectivo ni `cliente_id`.

- [ ] **Step 4: Implementar análisis**

Guardar temporal, llamar al adaptador, normalizar, buscar proveedor activo por nombre normalizado y devolver la propuesta. Ante error de IA conservar temporal para reintento hasta el TTL, pero no persistir viaje/evidencia.

- [ ] **Step 5: Implementar confirmación transaccional e idempotente**

Validar token, configuración y proveedor; fijar `numero_remision=''`, `cliente_id=None`, `pesaje_unico=True`, `neto_origen=0`; crear viaje con `commit=False`, promover archivo, crear `ViajeImagen` con expiración `now+60 días` y confirmar una sola vez. En error, rollback DB y archivo promovido. Buscar primero por `token_hash` para repetir respuesta sin duplicar.

- [ ] **Step 6: Implementar lectura autenticada**

Resolver evidencia por ID, comprobar `viaje.empleado_id == current_user.id` o `current_user.id in ADMIN_USER_IDS`, y devolver `FileResponse` con nombre seguro y `Cache-Control: private`.

- [ ] **Step 7: Ejecutar backend completo**

Run: `py -m unittest discover -s backend -p "test_*.py" -v`

Expected: PASS, sin llamadas reales a MiniMax.

- [ ] **Step 8: Commit**

```powershell
git add backend/trip_image_service.py backend/schemas.py backend/main.py backend/test_trip_image_api.py
git commit -m "feat: analizar y confirmar viajes desde imagen"
```

---

### Task 8: Programar limpieza idempotente sin borrar antes de tiempo

**Files:**
- Modify: `backend/scheduler.py`
- Modify: `backend/test_image_storage.py`

- [ ] **Step 1: Escribir pruebas de limpieza**

```python
def test_cleanup_borra_confirmadas_vencidas_y_conserva_vigentes(self):
    result = cleanup_trip_images(self.db, self.storage, now=NOW)
    self.assertEqual(result.deleted_confirmed, 1)
    self.assertTrue(self.valid_path.exists())
    self.assertFalse(self.expired_path.exists())
```

Agregar temporal abandonado, archivo ya ausente y segunda ejecución.

- [ ] **Step 2: Verificar fallo e implementar job**

Run: `py -m unittest backend.test_image_storage -v`

Expected antes: FAIL. Agregar `cleanup_trip_images` y registrar un job diario con `id='trip_image_cleanup'`, `replace_existing=True`, máximo una instancia y retención obtenida de `VIAJE_IMAGE_RETENTION_DAYS` default 60.

- [ ] **Step 3: Verificar idempotencia**

Run: `py -m unittest backend.test_image_storage -v`

Expected: PASS al ejecutar limpieza dos veces.

- [ ] **Step 4: Commit**

```powershell
git add backend/scheduler.py backend/test_image_storage.py
git commit -m "feat: limpiar evidencias de viaje vencidas"
```

---

### Task 9: Crear contrato frontend y reglas de revisión

**Files:**
- Create: `frontend/src/services/tripImage.js`
- Create: `frontend/src/services/tripImageReview.js`
- Create: `frontend/tests/tripImage.test.js`

- [ ] **Step 1: Escribir pruebas Node fallidas**

```javascript
test('buildConfirmPayload usa configuracion y no chofer OCR', () => {
  const payload = buildConfirmPayload(PROPOSAL, {
    user: { id: 51 }, defaultPatente: 'AAPV628', defaultUnidadNegocio: '19'
  })
  assert.equal(payload.patente, 'AAPV628')
  assert.equal(payload.unidad_negocio_id, 19)
  assert.equal(payload.pesaje_unico, true)
  assert.equal(payload.neto_origen, 0)
  assert.equal(payload.cliente_id, undefined)
  assert.equal(payload.chofer_id, undefined)
})
```

Agregar configuración incompleta, campos editables, form-data de imagen y mensajes de error API.

- [ ] **Step 2: Verificar fallo**

Run: `cd frontend; npm test`

Expected: FAIL por módulos inexistentes.

- [ ] **Step 3: Implementar helpers y cliente Axios**

`analyzeTripImage(file)`, `confirmTripImage(payload)` y `tripImageUrl(id)` usan `API_URL`; análisis usa `FormData`. `buildConfirmPayload` usa localStorage sólo para patente/unidad y no encola offline. Mantener pesos en TN con tres decimales en la revisión.

- [ ] **Step 4: Ejecutar pruebas frontend**

Run: `cd frontend; npm test`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/services/tripImage.js frontend/src/services/tripImageReview.js frontend/tests/tripImage.test.js
git commit -m "feat: preparar revision frontend de viajes OCR"
```

---

### Task 10: Implementar pantalla separada y acceso desde Nuevo Registro

**Files:**
- Create: `frontend/src/views/TripImageUpload.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/views/NewTrip.vue:253-274`
- Modify: `frontend/tests/tripImage.test.js`

- [ ] **Step 1: Agregar pruebas estáticas/funcionales de navegación**

Comprobar que la ruta requiere autenticación, que el botón apunta a `/new-trip/image` y que el formulario manual conserva su submit. Probar el state machine puro `selecting -> processing -> reviewing -> confirming -> success/error` mediante los helpers exportados.

- [ ] **Step 2: Verificar fallo**

Run: `cd frontend; npm test`

Expected: FAIL por ruta/vista ausentes.

- [ ] **Step 3: Construir `TripImageUpload.vue`**

La vista debe incluir:

- input `accept="image/jpeg,image/png,image/webp"` con `capture="environment"`;
- preview local antes del envío y original autenticado después de confirmar;
- progreso y botón de cancelar/reintentar;
- fecha, remito FGPY, proveedor, bruto, tara, neto y observaciones editables;
- chofer, patente y unidad en controles de sólo lectura identificados como configuración;
- advertencia no bloqueante ante patente/chofer OCR diferentes;
- bloqueo explícito si falta configuración o proveedor único;
- botón `Confirmar y guardar` que llama directamente a confirmación online;
- retorno a Nuevo Registro tras éxito, sin usar `sync.saveRecord`.

- [ ] **Step 4: Agregar botón independiente**

En `NewTrip.vue`, colocar una tarjeta azul/verde propia `Cargar desde foto` antes de la tarjeta de carretón y antes de `<form>`. No insertar el botón dentro del formulario ni reutilizar el botón `Guardar Registro`.

- [ ] **Step 5: Ejecutar pruebas y build blindado**

Run: `cd frontend; npm run verify`

Expected: pruebas PASS, build PASS y CSS procesado.

- [ ] **Step 6: Inspección móvil manual local**

Run: `cd frontend; npm run dev -- --host 0.0.0.0`

Verificar a ancho 390 px: botones separados, imagen legible, campos sin overflow, estados loading/error, tema oscuro y navegación atrás. Adjuntar captura a la evidencia del issue, no al repositorio salvo pedido expreso.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src/views/TripImageUpload.vue frontend/src/router/index.js frontend/src/views/NewTrip.vue frontend/tests/tripImage.test.js
git commit -m "feat: agregar pantalla separada de carga por imagen"
```

---

### Task 11: Documentar configuración y validar el flujo completo local

**Files:**
- Modify: `README.md`
- Modify: `backend/.env.example` (crear si no existe; nunca copiar valores reales)
- Test: `backend/test_trip_image_api.py`

- [ ] **Step 1: Documentar variables sin secretos**

```dotenv
MINIMAX_API_KEY=
MINIMAX_VISION_COMMAND=uvx minimax-coding-plan-mcp -y
MINIMAX_VISION_TIMEOUT_SECONDS=90
VIAJE_IMAGE_STORAGE_DIR=/var/lib/registro_viajes/images
VIAJE_IMAGE_MAX_BYTES=10485760
VIAJE_IMAGE_RETENTION_DAYS=60
IMAGE_TOKEN_SECRET=
```

Documentar instalación de `uv`, creación del directorio, migración/verify SQL y rollback operativo mediante backup previo (no incluir un rollback destructivo automático).

- [ ] **Step 2: Ejecutar suite completa**

Run: `py -m unittest discover -s backend -p "test_*.py" -v`

Expected: PASS.

Run: `cd frontend; npm run verify`

Expected: PASS y ningún CSS sin procesar.

- [ ] **Step 3: Ejecutar prueba real controlada de MiniMax**

Con `MINIMAX_API_KEY` ya cargada localmente, ejecutar un comando de smoke que analice la imagen de muestra sin confirmar ni escribir DB. Verificar `002-003-0003677`, `49.690`, `17.080`, `32.610` y Alcogreen. No imprimir la clave ni la respuesta cruda completa.

- [ ] **Step 4: Probar confirmación en SQLite aislado**

Usar copia temporal de la imagen y base SQLite de pruebas; confirmar y consultar que exista exactamente un viaje/evidencia, `cliente_id IS NULL`, origen cero, producción `32.61` y expiración a 60 días. Repetir confirmación y comprobar que no aumenta el conteo.

- [ ] **Step 5: Commit**

```powershell
git add README.md backend/.env.example backend/test_trip_image_api.py
git commit -m "docs: documentar operacion de carga OCR"
```

---

### Task 12: Auditar, actualizar el issue y preparar despliegue

**Files:**
- No source changes expected; any correction must receive its own tested commit.

- [ ] **Step 1: Revisar alcance y worktree**

Run: `git status -sb; git diff origin/main...HEAD --check; git log --oneline origin/main..HEAD`

Expected: sólo cambios de la funcionalidad y los artefactos locales no seguidos conocidos.

- [ ] **Step 2: Ejecutar verificación final fresca**

Run: `py -m unittest discover -s backend -p "test_*.py" -v`

Run: `cd frontend; npm ci; npm run verify`

Expected: ambas suites y build PASS desde dependencias reproducibles.

- [ ] **Step 3: Validar artefacto frontend**

Comprobar que `frontend/dist/assets/*.css` supera `verify-built-css.mjs`, que el HTML referencia archivos existentes y que el bundle contiene la ruta `/new-trip/image`.

- [ ] **Step 4: Actualizar GitHub issue #12**

Agregar un comentario con decisiones finales (`pesaje_unico`, cliente null, proveedor por búsqueda, configuración móvil, 60 días), commits, resultados de pruebas y pasos pendientes de producción. No cerrar hasta validar producción.

- [ ] **Step 5: Preparar despliegue reversible en `fasa_195`**

Antes de copiar:

1. Verificar `git status`, servicio, health, espacio y esquema real.
2. Crear backup fechado de código, frontend vigente, `.env` y tablas afectadas.
3. Instalar/verificar `uvx` y probar MiniMax sin DB.
4. Crear `/var/lib/registro_viajes/images` con dueño/permisos del servicio.
5. Aplicar y verificar la migración SQL.
6. Copiar código y `frontend/dist` excluyendo logs, `.env`, `.git`, `.codegraph`, `.cursor` y `.superpowers`.
7. Pedir al usuario el reinicio si `sudo systemctl restart viajes.service` lo requiere.

- [ ] **Step 6: Smoke test de producción**

Verificar servicio activo, `/api/health`, home y CSS público. Con un operador de prueba: analizar la imagen, revisar datos, confirmar una vez, consultar la imagen autenticada y comprobar en DB el viaje/evidencia exactos. Eliminar el registro de prueba sólo si fue acordado de antemano; en otro caso marcarlo claramente como prueba.

- [ ] **Step 7: Cerrar issue sólo con evidencia**

Comentar URLs/estado, IDs del registro de prueba, comprobación DB sin datos sensibles, fecha de expiración y resultados de smoke. Cerrar #12 únicamente si todo pasó; si el reinicio necesita sudo, dejar el comando exacto al usuario y mantener el issue abierto.

---

## Matriz de aceptación final

| Requisito | Evidencia requerida |
|---|---|
| Botón separado | Captura móvil + prueba de ruta/formulario |
| MiniMax backend-only | búsqueda de bundle/logs sin clave + prueba adaptador |
| Sin escritura antes de confirmar | conteo DB antes/después de análisis |
| Pesaje único | fila DB con origen 0, destino y producción esperados |
| Configuración del celular | payload frontend + fila con usuario/patente/unidad vigentes |
| Alcogreen proveedor | resolución por nombre y `proveedor_id` activo |
| Cliente vacío | `cliente_id IS NULL` |
| Imagen 60 días | evidencia con `expires_at` + endpoint autenticado |
| Limpieza | pruebas idempotentes de vencidas/vigentes |
| CSS reparado | build verifier + CSS público procesado |
| Flujo manual intacto | suite regresión + smoke manual |
