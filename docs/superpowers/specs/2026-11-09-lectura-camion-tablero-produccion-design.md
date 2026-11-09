# Lectura de km/horas del camión en tablero_produccion

- **Fecha:** 2026-11-09
- **Estado:** aprobado por el usuario
- **Alcance:** formulario "Nuevo Registro" (viajes normales)

## Objetivo

Cargar en cada viaje normal la lectura del odómetro (km) o del horómetro (horas) del
camión, y persistirla en `tablero_produccion`. Hoy los viajes normales no guardan
ninguna lectura: `trip_service.py` escribe `hr_inicio=0.0, hr_fin=0.0`.

## Contexto del modelo actual

`tablero_produccion` ya tiene `hr_inicio` y `hr_fin`, pero tienen otra semántica:

- Son un **par de tramo**: el flujo de carretón escribe `km_inicial`/`km_final` y
  calcula `produccion = km_final - km_inicio` (`backend/main.py:1250-1252`).
- Los viajes normales los dejan en `0.0` (`backend/trip_service.py:170`).
- Los tres lectores de esas columnas (`backend/main.py:1217`, `1397`, `1430`) filtran
  por `tabla == 'movimiento_carreton'`, así que hoy no se mezclan.

### Por qué NO se reusa `hr_fin`

Se evaluó y se descartó reusar `hr_fin` para la lectura:

1. **Un valor solo no alcanza.** La lectura es acumulada (odómetro al momento del
   viaje), no un tramo. En `hr_fin` habría que guardar la lectura con `hr_inicio = 0`,
   y cualquier reporte que calcule `hr_fin - hr_inicio` obtendría basura.
2. **Unidad distinta en la misma columna.** `hr_fin` está etiquetada explícitamente
   como KM en el flujo de carretón (`backend/main.py:1398` la expone como `km_final`).
   Un camión medido en horas escribiría horas donde el otro flujo espera kilómetros.
3. **`hr_fin` es `Float NOT NULL default 0`** (`backend/models.py:146`): "no se
   registró lectura" quedaría indistinguible de una lectura real de 0.
4. **Radio de impacto.** `tablero_produccion` es la tabla legacy compartida con
   FGPY/Kobo. Una columna nullable nueva es inerte para todas las consultas
   actuales; cambiar el significado de una columna existente no lo es.

### Por qué NO se reusa `equipos.ult_hr_km`

`equipos.ult_hr_km` (`backend/models.py:105`) existe y está muerto: nadie lo lee ni
escribe desde la app (solo `seed_data.py` y los tests). Su nombre significa
"último hr/km del equipo". Sin embargo **no se usa como referencia de validación**:
sus valores en producción son legacy y desconocidos, y uno alto podría bloquear un
registro legítimo. La referencia de validación es exclusivamente nuestra propia cadena.

## Decisiones

| Decisión | Valor | Motivo |
|---|---|---|
| Pantalla | Solo "Nuevo Registro" | El flujo OCR queda fuera: sus viajes guardan NULL |
| Semántica | Lectura acumulada del odómetro/horómetro | El km del viaje se deriva por diferencia contra el viaje anterior |
| Modelo en BD | Columna nueva `lectura_camion` + `unidad_lectura` | Evita mezclar con `hr_fin` (ver arriba) |
| Unidad | Fija por camión (`equipos.unidad_hr_km`), la resuelve el servidor | El cliente no puede mandar una unidad falsa; el admin corrige sin reescribir historia |
| Reglas | Obligatorio en el formulario + no menor al anterior (con override) | Coherente con el flujo de carretón ya existente |
| Payload legacy | Tolerado: si falta la lectura, se guarda NULL | No rompe app vieja ni viajes offline pendientes |
| Interruptor | `VIAJE_EXIGIR_LECTURA_CAMION` (default `true`) | Permite relajar en producción sin redesplegar |

## Modelo de datos

### `tablero_produccion` — columnas nuevas

```sql
lectura_camion  DECIMAL(10,2) NULL   -- lectura acumulada; NULL = no registrada
unidad_lectura  VARCHAR(3)   NULL   -- snapshot de la unidad al momento del viaje
```

- `lectura_camion` nullable: distingue "sin lectura" de una lectura real de 0.
- `unidad_lectura` es un **snapshot**, no una referencia viva. Si el admin cambia la
  unidad de un camión, los viajes históricos conservan la unidad con la que se
  registraron, y la comparación de monotonía se desactiva para las unidades
  distintas en lugar de comparar números sin sentido.

### `equipos` — columna nueva

```sql
unidad_hr_km  VARCHAR(3) NOT NULL DEFAULT 'km'   -- 'km' | 'hs'
```

Define en qué unidad lee ese camión. El admin la setea por SQL (no hay pantalla de
administración de equipos en la app):

```sql
UPDATE equipos SET unidad_hr_km = 'hs' WHERE id = <id_camion_horometro>;
```

Default `'km'` porque es el caso mayoritario y no rompe nada si nadie lo ajusta.

### Lo que NO se toca

- `tablero_produccion.hr_inicio` / `hr_fin`: siguen siendo del flujo de carretón.
- `equipos.ult_hr_km`: queda como está (legacy, sin uso por la app).

## Reglas de validación

### Backend (autoritativo)

1. Si `lectura_camion` viene en el payload:
   - Debe ser numérico y `> 0`. Rechazo 400.
   - La unidad se resuelve desde `equipos.unidad_hr_km` del equipo resuelto por
     patente. El cliente no manda la unidad.
   - Se busca la última lectura del mismo `equipo_id` con la **misma**
     `unidad_lectura`, ordenando por `fecha DESC, id DESC`.
   - Si la lectura nueva es **menor** que esa referencia y no viene
     `permitir_lectura_menor`, se rechaza 400 con el detalle del valor anterior.
2. Si `lectura_camion` **no** viene en el payload:
   - Se guarda NULL. No se rechaza. Esto cubre app vieja y viajes offline
     pendientes de la versión anterior.

El interruptor `VIAJE_EXIGIR_LECTURA_CAMION` (default `true`) gobierna el frontend
(que el campo sea obligatorio en el formulario). El backend siempre tolera el
payload ausente: el rechazo vive en la UI, que es donde el chofer puede corregir.

`permitir_lectura_menor` es el espejo de `permitir_km_inicial_menor` que ya usa el
flujo de carretón (`backend/main.py:1225`): el chofer confirma y el registro se
guarda igual, dejando rastro en el log.

### Frontend

- El campo se muestra siempre. Si el interruptor está activo, es obligatorio.
- Precarga la última lectura conocida del camión para que el chofer parta de ahí.
- Si la lectura cargada es menor que la anterior, muestra un `Swal` de confirmación
  ("Guardar igual"), igual que hace `CarretonMove.vue:171-185`.
- Guarda en `localStorage` la última lectura por equipo para funcionar offline, con
  el mismo patrón que `last_km_carreton_${equipoId}`.
- Al crear un registro pendiente offline, toma como referencia las lecturas
  pendientes locales del mismo equipo, para no rechazar un registro válido.

## Componentes

### Backend

| Archivo | Cambio |
|---|---|
| `backend/models.py` | `TableroProduccion.lectura_camion`, `TableroProduccion.unidad_lectura`; `Equipo.unidad_hr_km` |
| `backend/schemas.py` | `RegistroViajeCreate.lectura_camion`, `RegistroViajeCreate.permitir_lectura_menor`; `Equipo.unidad_hr_km` en `EquipoBase`; `HistorialViajeItem` expone la lectura |
| `backend/trip_service.py` | Resolución de unidad desde el equipo, validación de monotonía, persistencia |
| `backend/main.py` | `GET /api/registro-viaje/ultima-lectura?equipo_id=`; el flag `exigir_lectura_camion` en `GET /api/app-version` |
| `backend/migrations/20261109_add_lectura_camion.sql` | Migración idempotente de las 3 columnas |
| `backend/migrations/20261109_verify_lectura_camion.sql` | Verificación de solo lectura |

El endpoint de última lectura es análogo a `GET /api/movimientos-carreton/ultimo`
(`backend/main.py:1407`), que ya resuelve el mismo problema para el carretón.

**Resolución patente → equipo en el frontend:** `NewTrip.vue` no maneja `equipo_id`;
trabaja con `patente` (viene de Ajustes, campo deshabilitado en el formulario). El
frontend lo resuelve contra el catálogo con `findEquipoByPatente`, que ya existe en
`frontend/src/services/criticalScreens.js` y normaliza el formato (`AB 123 CD` =
`AB123CD`). Es la misma función que usa `CarretonMove.vue`. Si no encuentra el
equipo, el frontend no precarga nada y el backend igual resuelve la unidad al
guardar, porque `_equipment()` (`backend/trip_service.py:62`) busca por patente
exacta o compacta.

### Frontend

| Archivo | Cambio |
|---|---|
| `frontend/src/views/NewTrip.vue` | Input de lectura + estado de la última lectura + confirmación de menor |
| `frontend/src/services/criticalScreens.js` | `normalizeLectura`, `buildViajePayload`, `getPendingViajeLastLectura` |
| `frontend/src/services/syncPendingRecord.js` | `lectura_camion` numérico en el payload; `permitir_lectura_menor` |
| `frontend/src/views/History.vue` | Muestra la lectura en cada viaje |

**De dónde saca el frontend la unidad y el interruptor:**

- **Unidad:** viene en el catálogo `/api/equipos`, porque `unidad_hr_km` se agrega a
  `EquipoBase` (`backend/schemas.py`) y por lo tanto viaja en el `Equipo` que ya
  devuelve ese endpoint. El frontend la usa solo para **etiquetar** el campo
  ("Lectura (km)" / "Lectura (hs)"); nunca la manda. El valor que se guarda lo
  decide el servidor.
- **Interruptor:** `GET /api/app-version` devuelve además `exigir_lectura_camion`.
  `NewTrip.vue` lo pide al montar y lo cachea en `localStorage`, para que offline el
  formulario siga comportándose igual que online.

El catálogo de equipos se cachea en IndexedDB (`frontend/src/stores/catalog.js`), así
que un dispositivo offline puede tener la unidad desactualizada si el admin la cambió
hace poco. No afecta la corrección de los datos: el backend sigue resolviendo la
unidad desde la base. Solo afecta la etiqueta mostrada al chofer.

## Migración

`backend/migrations/20261109_add_lectura_camion.sql`, con el mismo estilo idempotente
de las migraciones previas (`20260713_add_trip_image_ocr.sql`): procedimiento
almacenado que consulta `information_schema.COLUMNS` y solo altera si la columna no
existe. Ninguna columna es `NOT NULL` sin default, así que no hay que tocar filas
existentes.

Aplicación en producción con el ritual del README (backup previo, `mysqldump`,
`mysql < migración`, luego `mysql --table < verificación`).

**Orden obligatorio:** la migración se aplica **antes** de desplegar el backend
nuevo. El backend nuevo selecciona `lectura_camion` y `unidad_lectura` en cada
viaje: si las columnas no existen todavía, el `SELECT` falla con
`OperationalError` y la pantalla de registro de viajes queda caída. La app vieja
no las toca, así que aplicar la migración con la app corriendo es seguro.

Por ese motivo el deploy se hace en dos pasos: (1) migración, (2) backend +
frontend.

> La base de producción (`srv1723.hstgr.io`) rechaza conexiones desde esta red por
> allowlist de IP. La migración queda prepared; la aplica el operador en el servidor.

## Pruebas

**Backend** — `backend/test_trip_lectura_camion.py`, con SQLite aislado (mismo patrón
que `backend/test_admin_dashboard.py`):

- Guarda la lectura con la unidad resuelta desde el equipo.
- Lee una lectura mayor a la anterior: OK.
- Lee una lectura menor a la anterior: 400 con el detalle del valor anterior.
- Lee una lectura menor con `permitir_lectura_menor`: OK.
- Payload sin `lectura_camion`: OK, se guarda NULL.
- Valor no numérico o `<= 0`: 400.
- Unidad distinta: no compara contra la lectura de otra unidad.
- La comparación ignora viajes de carretón (`tabla='movimiento_carreton'`) y viajes
  OCR (sin lectura).

**Frontend** — `frontend/tests/criticalScreens.test.js`:

- `normalizeLectura` acepta `"1.234,5"`, `"1234.5"` y `"1234"`.
- `buildViajePayload` incluye `lectura_camion` como número y `permitir_lectura_menor`.
- `getPendingViajeLastLectura` toma la lectura pendiente más reciente del equipo.

**Verificación completa:**

```powershell
py -m pytest backend -q
Set-Location frontend
npm run verify
```

## Fuera de alcance

- El flujo OCR ("Cargar desde foto"): sus viajes se guardan con `lectura_camion` NULL
  y no participan de la cadena de monotonía.
- El flujo de carretón: sigue con su propio par `hr_inicio`/`hr_fin`.
- Pantalla de administración de equipos para setear `unidad_hr_km`: se hace por SQL.
- Reportes que calculen km por viaje a partir de las diferencias de lectura.
- `equipos.ult_hr_km`: no se lee ni se escribe.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Choferes con trucks que no reportan odómetro | Interruptor `VIAJE_EXIGIR_LECTURA_CAMION` |
| App vieja o viaje offline pendiente sin el campo | Backend lo tolera y guarda NULL |
| Migración aplicada después del deploy | Orden obligatorio migración → deploy (§ Migración); el backend nuevo selecciona esas columnas en cada viaje y falla si no existen |
| Cambio de unidad de un camión | `unidad_lectura` snapshot preserva la historia; la comparación se desactiva entre unidades distintas |
| Falso bloqueo por lectura mal digitada | Override `permitir_lectura_menor` con confirmación explícita del chofer |
