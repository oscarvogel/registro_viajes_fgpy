# Lectura de km/horas del camión en tablero_produccion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que cada viaje normal registre la lectura del odómetro (km) o del horómetro (horas) del camión y la persista en `tablero_produccion`.

**Architecture:** Dos columnas nuevas nullable en `tablero_produccion` (`lectura_camion`, `unidad_lectura`) y una en `equipos` (`unidad_hr_km`). El cliente manda solo el número; el backend resuelve la unidad desde el equipo y la graba como snapshot. La monotonía ("no menor al anterior") se valida contra el último viaje del mismo equipo **con la misma unidad**. El backend es tolerante con el payload ausente; la obligatoriedad vive en el frontend, gobernada por `VIAJE_EXIGIR_LECTURA_CAMION`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Pydantic v2, pytest. Vue 3 + Vite + Pinia, `node --test` y Vitest.

**Spec:** `docs/superpowers/specs/2026-11-09-lectura-camion-tablero-produccion-design.md`

## Global Constraints

- Rama de trabajo: `feature/lectura-camion-tablero-produccion` (ya creada, spec ya commiteado).
- **La migración se aplica ANTES del deploy del backend.** El backend nuevo selecciona `lectura_camion` y `unidad_lectura` en cada viaje y falla con `OperationalError` si las columnas no existen.
- No se modifica `tablero_produccion.hr_inicio` ni `hr_fin`: son el par de tramo del flujo de carretón.
- No se lee ni se escribe `equipos.ult_hr_km`: sus valores en producción son legacy y desconocidos, y no sirven como referencia de validación.
- El backend **nunca** rechaza por falta de `lectura_camion`: si el payload no la trae, se guarda NULL.
- La unidad la resuelve **siempre** el servidor desde `equipos.unidad_hr_km`. El cliente no manda la unidad.
- `unidad_lectura` es un snapshot: si el admin cambia la unidad de un camión, la comparación de monotía se desactiva entre unidades distintas en vez de comparar números sin sentido.
- Validación numérica: `lectura_camion` debe ser `> 0`. `<= 0` se rechaza con 400.
- El mensaje de error de monotía debe incluir la lectura anterior, para que el chofer sepa qué corregir.
- Convenciones de la app: los schemas de entrada usan `Optional[...] = None`; los endpoints usan el prefijo `@api_router`; los errores de negocio son `HTTPException(status_code=400, detail="...")`; los tests de backend son `unittest.TestCase` con SQLite aislado vía `DATABASE_URL` en `os.environ`; los tests de frontend son `node:test` con `node:assert/strict`.
- Los archivos de `.sql` de migración y verificación van en `backend/migrations/` con prefijo de fecha `20261109_`.
- La suite completa del backend se corre con `py -m pytest backend -q` desde la raíz del repo. La del frontend con `npm run verify` desde `frontend/`.

---

### Task 1: Columnas en los modelos y migraciones SQL

**Files:**
- Modify: `backend/models.py:89-105` (clase `Equipo`), `backend/models.py:196-203` (clase `TableroProduccion`)
- Create: `backend/migrations/20261109_add_lectura_camion.sql`
- Create: `backend/migrations/20261109_verify_lectura_camion.sql`
- Test: `backend/test_trip_lectura_camion.py`

**Interfaces:**
- Consumes: nada (tarea base).
- Produces:
  - `models.Equipo.unidad_hr_km: str` — `'km'` o `'hs'`, default `'km'`.
  - `models.TableroProduccion.lectura_camion: Decimal | None` — lectura acumulada; `NULL` = no registrada.
  - `models.TableroProduccion.unidad_lectura: str | None` — snapshot de `'km'` o `'hs'`.

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/test_trip_lectura_camion.py`:

```python
import sys
import unittest
from pathlib import Path


class LecturaCamionModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        backend_dir = Path(__file__).resolve().parent
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        import models

        cls.models = models

    def test_equipos_declara_unidad_hr_km_por_defecto_km(self):
        columna = self.models.Equipo.__table__.columns["unidad_hr_km"]
        self.assertFalse(columna.nullable)
        self.assertEqual(columna.default.arg, "km")

    def test_tablero_produccion_declara_lectura_camion_nullable(self):
        columna = self.models.TableroProduccion.__table__.columns["lectura_camion"]
        self.assertTrue(columna.nullable)

    def test_tablero_produccion_declara_unidad_lectura_nullable(self):
        columna = self.models.TableroProduccion.__table__.columns["unidad_lectura"]
        self.assertTrue(columna.nullable)

    def test_hr_inicio_y_hr_fin_no_cambian_de_semantica(self):
        tablero = self.models.TableroProduccion.__table__
        self.assertTrue(tablero.columns["hr_inicio"].nullable is False)
        self.assertTrue(tablero.columns["hr_fin"].nullable is False)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `py -m pytest backend/test_trip_lectura_camion.py -q`
Expected: FAIL con `KeyError: 'unidad_hr_km'`

- [ ] **Step 3: Agregar las columnas al modelo**

En `backend/models.py`, clase `Equipo`, después de la línea `ult_hr_km = Column(DECIMAL(10, 2), nullable=False, default=0.0)`:

```python
    unidad_hr_km = Column(String(3), nullable=False, default="km")
```

En `backend/models.py`, clase `TableroProduccion`, después de la línea `neto_destino = Column(DECIMAL(10, 2), nullable=False, default=0.0)`:

```python
    lectura_camion = Column(DECIMAL(10, 2), nullable=True)
    unidad_lectura = Column(String(3), nullable=True)
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `py -m pytest backend/test_trip_lectura_camion.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Escribir la migración**

Crear `backend/migrations/20261109_add_lectura_camion.sql`:

```sql
-- Agrega la lectura de km/horas del camion a los viajes normales.
-- Migracion idempotente: solo altera si la columna no existe.
-- Revisar y hacer backup antes de ejecutar (ver README).
-- Aplicar ANTES de desplegar el backend nuevo: este selecciona las columnas.

DELIMITER $$

DROP PROCEDURE IF EXISTS add_lectura_camion$$
CREATE PROCEDURE add_lectura_camion()
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE()
           AND TABLE_NAME = 'tablero_produccion'
           AND COLUMN_NAME = 'lectura_camion'
    ) THEN
        ALTER TABLE tablero_produccion
            ADD COLUMN lectura_camion DECIMAL(10, 2) NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE()
           AND TABLE_NAME = 'tablero_produccion'
           AND COLUMN_NAME = 'unidad_lectura'
    ) THEN
        ALTER TABLE tablero_produccion
            ADD COLUMN unidad_lectura VARCHAR(3) NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE()
           AND TABLE_NAME = 'equipos'
           AND COLUMN_NAME = 'unidad_hr_km'
    ) THEN
        ALTER TABLE equipos
            ADD COLUMN unidad_hr_km VARCHAR(3) NOT NULL DEFAULT 'km';
    END IF;
END$$

CALL add_lectura_camion()$$
DROP PROCEDURE add_lectura_camion$$

DELIMITER ;
```

- [ ] **Step 6: Escribir el script de verificación**

Crear `backend/migrations/20261109_verify_lectura_camion.sql`:

```sql
-- Verificacion de solo lectura de la migracion de lectura de camion.
-- Debe mostrar: lectura_camion nullable DECIMAL, unidad_lectura nullable VARCHAR,
-- unidad_hr_km NOT NULL DEFAULT 'km', y cero filas con lectura no nula.

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COALESCE(COLUMN_DEFAULT, '<NULL>') AS default_value
  FROM information_schema.COLUMNS
 WHERE TABLE_SCHEMA = DATABASE()
   AND TABLE_NAME = 'tablero_produccion'
   AND COLUMN_NAME IN ('lectura_camion', 'unidad_lectura')
 ORDER BY COLUMN_NAME;

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COALESCE(COLUMN_DEFAULT, '<NULL>') AS default_value
  FROM information_schema.COLUMNS
 WHERE TABLE_SCHEMA = DATABASE()
   AND TABLE_NAME = 'equipos'
   AND COLUMN_NAME = 'unidad_hr_km';

SELECT COUNT(*) AS filas_con_lectura
  FROM tablero_produccion
 WHERE lectura_camion IS NOT NULL;

SELECT COUNT(*) AS equipos_sin_unidad
  FROM equipos
 WHERE unidad_hr_km IS NULL OR unidad_hr_km NOT IN ('km', 'hs');
```

- [ ] **Step 7: Verificar que la migración es idempotente en SQLite (test)**

Agregar a `backend/test_trip_lectura_camion.py`:

```python
class LecturaCamionMigracionTest(unittest.TestCase):
    def test_migracion_es_idempotente_y_tiene_las_tres_columnas(self):
        sql = (Path(__file__).resolve().parent / "migrations" / "20261109_add_lectura_camion.sql").read_text(encoding="utf-8")

        self.assertIn("ADD COLUMN lectura_camion DECIMAL(10, 2) NULL", sql)
        self.assertIn("ADD COLUMN unidad_lectura VARCHAR(3) NULL", sql)
        self.assertIn("ADD COLUMN unidad_hr_km VARCHAR(3) NOT NULL DEFAULT 'km'", sql)
        # Las tres columnas se agregan solo si no existen.
        self.assertEqual(sql.count("IF NOT EXISTS"), 3)
        # Nunca se hace DROP de hr_inicio/hr_fin.
        self.assertNotIn("DROP COLUMN", sql)

    def test_script_de_verificacion_es_solo_lectura(self):
        sql = (Path(__file__).resolve().parent / "migrations" / "20261109_verify_lectura_camion.sql").read_text(encoding="utf-8")

        for verbo in ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "CREATE"):
            self.assertNotIn(verbo, sql.upper(), f"El script de verificacion no debe ejecutar {verbo}")
```

- [ ] **Step 8: Correr los tests y verificar que pasan**

Run: `py -m pytest backend/test_trip_lectura_camion.py -q`
Expected: PASS (6 tests)

- [ ] **Step 9: Commit**

```bash
git add backend/models.py backend/migrations/20261109_add_lectura_camion.sql backend/migrations/20261109_verify_lectura_camion.sql backend/test_trip_lectura_camion.py
git commit -m "feat(esquema): columnas lectura_camion y unidad_lectura en tablero_produccion

Agrega lectura_camion DECIMAL(10,2) NULL y unidad_lectura VARCHAR(3) NULL a
tablero_produccion, y unidad_hr_km VARCHAR(3) NOT NULL DEFAULT 'km' a equipos.

hr_inicio/hr_fin quedan intactos: son el par de tramo del flujo de carreton.
La migracion es idempotente y debe aplicarse antes del deploy del backend."
```

---

### Task 2: Validación y persistencia de la lectura en el servicio de viajes

**Files:**
- Modify: `backend/schemas.py:116-152` (`RegistroViajeCreate`), `backend/schemas.py:81-91` (`EquipoBase`/`Equipo`), `backend/schemas.py:351-359` (`HistorialViajeItem`)
- Modify: `backend/trip_service.py` (nuevas funciones + `_build_record` + `create_trip`)
- Test: `backend/test_trip_lectura_camion.py`

**Interfaces:**
- Consumes: `models.Equipo.unidad_hr_km`, `models.TableroProduccion.lectura_camion`, `models.TableroProduccion.unidad_lectura` (Task 1).
- Produces:
  - `schemas.RegistroViajeCreate.lectura_camion: Optional[float] = None`
  - `schemas.RegistroViajeCreate.permitir_lectura_menor: bool = False`
  - `schemas.Equipo.unidad_hr_km: str` (vía `EquipoBase`)
  - `schemas.HistorialViajeItem.lectura_camion: Optional[float] = None`
  - `schemas.HistorialViajeItem.unidad_lectura: Optional[str] = None`
  - `trip_service.UNIDAD_KM = "km"`, `trip_service.UNIDAD_HS = "hs"`
  - `trip_service.unidad_de_equipo(equipo) -> str` — normaliza a `'km'` o `'hs'`, con fallback `'km'`.
  - `trip_service.ultima_lectura(db, equipo_id, unidad) -> Optional[models.TableroProduccion]`
  - `trip_service.validar_lectura(db, registro, equipo) -> tuple[Optional[Decimal], Optional[str]]`

- [ ] **Step 1: Escribir el test que falla**

Agregar a `backend/test_trip_lectura_camion.py`:

```python
import os
import sys
import tempfile
import types
import unittest
from datetime import date, time
from pathlib import Path


class LecturaCamionBaseTest(unittest.TestCase):
    """Fixture compartida: base SQLite aislada con los datos minimos.

    Las clases de servicio y de endpoint heredan de aca. La base no define
    tests propios, asi que no se ejecutan por duplicado.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmpdir.name, "lectura_camion_test.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["ENABLE_ERROR_ALERT_EMAILS"] = "false"
        os.environ["JWT_SECRET_KEY"] = "test-secret-for-jwt-with-at-least-32-bytes"
        os.environ["JWT_ALGORITHM"] = "HS-256"
        os.environ["JWT_EXPIRE_MINUTES"] = "60"
        os.environ["AUTH_ENFORCEMENT_MODE"] = "compat"
        os.environ["ADMIN_USER_IDS"] = "1"

        backend_dir = Path(__file__).resolve().parent
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        self._stub_sentry()
        for module_name in ("main", "models", "database", "trip_service", "schemas"):
            sys.modules.pop(module_name, None)

        import database
        import models
        import schemas
        import trip_service

        self.database = database
        self.models = models
        self.schemas = schemas
        self.trip_service = trip_service

        models.Base.metadata.drop_all(bind=database.engine)
        models.Base.metadata.create_all(bind=database.engine)
        self.db = database.SessionLocal()
        self._seed()

    def tearDown(self):
        self.db.close()
        self.database.engine.dispose()
        self.tmpdir.cleanup()

    def _stub_sentry(self):
        sentry_sdk = types.ModuleType("sentry_sdk")
        sentry_sdk.init = lambda *args, **kwargs: None

        integrations = types.ModuleType("sentry_sdk.integrations")
        logging_integration = types.ModuleType("sentry_sdk.integrations.logging")
        starlette_integration = types.ModuleType("sentry_sdk.integrations.starlette")
        fastapi_integration = types.ModuleType("sentry_sdk.integrations.fastapi")

        class _Integration:
            def __init__(self, *args, **kwargs):
                pass

        logging_integration.LoggingIntegration = _Integration
        starlette_integration.StarletteIntegration = _Integration
        fastapi_integration.FastAPIIntegration = _Integration

        sys.modules.setdefault("sentry_sdk", sentry_sdk)
        sys.modules.setdefault("sentry_sdk.integrations", integrations)
        sys.modules.setdefault("sentry_sdk.integrations.logging", logging_integration)
        sys.modules.setdefault("sentry_sdk.integrations.starlette", starlette_integration)
        sys.modules.setdefault("sentry_sdk.integrations.fastapi", fastapi_integration)

    def _seed(self):
        self.empleado = self.models.Empleado(
            id=1, nombre="Ana", apellido="Pérez", email="ana@example.com",
            documento="12345678", fecha_contratacion=date(2024, 1, 1),
            activo=True, porcentaje=0.0,
        )
        self.unidad = self.models.UnidadNegocio(
            id=1, descripcion="Transporte Chip", prefijo="TC", activo=True, codigo_kobo="TC",
        )
        self.cliente = self.models.Cliente(id=1, razon_social="Alcogreen", activo=True)
        self.proveedor = self.models.Proveedor(id=1, razon_social="Forestal Paraguay", activo=True)
        self.equipo_km = self.models.Equipo(
            id=10, descripcion="Scania", patente="ABC123", nro_chasis="CH10",
            nro_motor="MO10", tipo_movil_id=1, movil_asociado=0, activo=True,
            ult_hr_km=0, unidad_hr_km="km",
        )
        self.equipo_hs = self.models.Equipo(
            id=11, descripcion="Tractor", patente="HHS789", nro_chasis="CH11",
            nro_motor="MO11", tipo_movil_id=1, movil_asociado=0, activo=True,
            ult_hr_km=0, unidad_hr_km="hs",
        )
        self.db.add_all([self.empleado, self.unidad, self.cliente, self.proveedor, self.equipo_km, self.equipo_hs])
        self.db.commit()

    def _registro(self, **overrides):
        datos = dict(
            fecha_remision=date(2026, 11, 9),
            fecha_recepcion=date(2026, 11, 9),
            proveedor_id=1,
            cliente_id=1,
            numero_remision="002-003-0000001",
            numero_remision_fpv="002-003-0000002",
            peso_bruto_origen=50.0,
            tara_origen=18.0,
            neto_origen=32.0,
            peso_bruto_destino=50.0,
            tara_destino=18.0,
            neto_destino=32.0,
            chofer_id=1,
            patente="ABC123",
            unidad_negocio_id=1,
        )
        datos.update(overrides)
        return self.schemas.RegistroViajeCreate(**datos)

    def _crear_viaje(self, **overrides):
        registro = self._registro(**overrides)
        return self.trip_service.create_trip(self.db, registro, self.empleado)


class LecturaCamionServicioTest(LecturaCamionBaseTest):
    def test_guarda_la_lectura_con_la_unidad_resuelta_del_equipo(self):
        viaje = self._crear_viaje(lectura_camion=1234.5)
        self.assertEqual(float(viaje.lectura_camion), 1234.5)
        self.assertEqual(viaje.unidad_lectura, "km")

    def test_equipo_con_horometro_guarda_la_unidad_hs(self):
        registro = self._registro(patente="HHS789", numero_remision="002-003-0000003")
        viaje = self.trip_service.create_trip(self.db, registro, self.empleado)
        self.assertEqual(viaje.unidad_lectura, "hs")

    def test_payload_sin_lectura_se_guarda_como_null_y_no_falla(self):
        viaje = self._crear_viaje()
        self.assertIsNone(viaje.lectura_camion)
        self.assertIsNone(viaje.unidad_lectura)

    def test_lectura_menor_a_la_anterior_es_rechazada(self):
        self._crear_viaje(lectura_camion=5000, numero_remision="002-003-0000011")

        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as caught:
            self._crear_viaje(lectura_camion=4000, numero_remision="002-003-0000012")

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("5000", str(caught.exception.detail))

    def test_lectura_menor_con_permiso_se_guarda(self):
        self._crear_viaje(lectura_camion=5000, numero_remision="002-003-0000021")
        viaje = self._crear_viaje(lectura_camion=4000, numero_remision="002-003-0000022", permitir_lectura_menor=True)
        self.assertEqual(float(viaje.lectura_camion), 4000)

    def test_lectura_no_positiva_es_rechazada(self):
        from fastapi import HTTPException
        for valor in (0, -10):
            with self.assertRaises(HTTPException) as caught:
                self._crear_viaje(lectura_camion=valor, numero_remision="002-003-0000031")
            self.assertEqual(caught.exception.status_code, 400)

    def test_no_compara_contra_lecturas_de_otra_unidad(self):
        # El admin cambia la unidad del camion: la lectura anterior quedo en 'km'
        # y la nueva es 'hs', asi que no se comparan numeros sin sentido.
        self._crear_viaje(lectura_camion=99999, numero_remision="002-003-0000041")

        self.equipo_km.unidad_hr_km = "hs"
        self.db.commit()

        viaje = self._crear_viaje(lectura_camion=5, numero_remision="002-003-0000042")
        self.assertEqual(float(viaje.lectura_camion), 5)
        self.assertEqual(viaje.unidad_lectura, "hs")

    def test_si_mantiene_la_unidad_sigue_comparando(self):
        self._crear_viaje(lectura_camion=99999, numero_remision="002-003-0000061")

        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as caught:
            self._crear_viaje(lectura_camion=5, numero_remision="002-003-0000062")

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("99999", str(caught.exception.detail))

    def test_no_compara_contra_movimientos_de_carreton(self):
        # Un movimiento de carreton usa hr_fin, no lectura_camion: no debe entrar en la cadena.
        self.db.add(self.models.TableroProduccion(
            fecha=date(2026, 11, 8),
            unidad_negocio_id=1, empleado_id=1, equipo_id=10,
            hr_inicio=8000.0, hr_fin=9000.0, produccion=1000.0,
            unidad_produccion_id=7, remito=0, remito2=0, hora=time(8, 0), turno="dia",
            predio_id=1, tipo_operacion_id=21, origen_destino_id=1, codigo_tabla=0,
            hrs_no_operativas=0, carga_piso=0, plantas=0, lenia_seca=0,
            carga_rollo=0, carga_lenia=0, coeficiente=1.0, altura=0.0, ancho=0.0,
            cantidad_estibas=0.0, largo_madera=0.0, carros=0, tarifa=0.0, tarifa_empresa=0.0,
            modificado=False, tabla="movimiento_carreton",
            neto_origen=0, bruto_destino=0, tara_destino=0, neto_destino=0,
        ))
        self.db.commit()

        viaje = self._crear_viaje(lectura_camion=100, numero_remision="002-003-0000051")
        self.assertEqual(float(viaje.lectura_camion), 100)
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `py -m pytest backend/test_trip_lectura_camion.py -q`
Expected: FAIL con `TypeError: RegistroViajeCreate() got an unexpected keyword argument 'lectura_camion'`

- [ ] **Step 3: Agregar los campos a los schemas**

En `backend/schemas.py`, clase `RegistroViajeCreate`, después de `observaciones: Optional[str] = None`:

```python
    # Lectura acumulada del odometro/horometro del camion.
    # Opcional a proposito: el backend tolera el payload ausente (app vieja,
    # viajes offline pendientes) y guarda NULL.
    lectura_camion: Optional[float] = None
    # Permite guardar una lectura menor a la anterior, con confirmacion del chofer.
    permitir_lectura_menor: bool = False
```

En `backend/schemas.py`, clase `EquipoBase`:

```python
class EquipoBase(BaseModel):
    descripcion: str
    patente: str
    tipo_movil_id: int
    unidad_hr_km: str = "km"
```

En `backend/schemas.py`, clase `HistorialViajeItem`, después de `observaciones: Optional[str] = None`:

```python
    lectura_camion: Optional[float] = None
    unidad_lectura: Optional[str] = None
```

- [ ] **Step 4: Implementar la validación en `trip_service.py`**

En `backend/trip_service.py`, después de `DB_WEIGHT_SCALE = Decimal("0.01")`:

```python
UNIDAD_KM = "km"
UNIDAD_HS = "hs"
UNIDADES_VALIDAS = (UNIDAD_KM, UNIDAD_HS)
```

Agregar estas funciones al final del archivo:

```python
def unidad_de_equipo(equipo):
    """Devuelve la unidad de medida del equipo: 'km' o 'hs'.

    La unidad es fija por camion y la define el admin en equipos.unidad_hr_km.
    Si el valor guardado no es valido se cae a 'km'.
    """
    valor = str(getattr(equipo, "unidad_hr_km", None) or UNIDAD_KM).strip().lower()
    return valor if valor in UNIDADES_VALIDAS else UNIDAD_KM


def ultima_lectura(db, equipo_id, unidad):
    """Ultimo viaje del equipo con lectura registrada en la misma unidad.

    Ignora los movimientos de carreton (usan hr_fin) y los viajes sin lectura.
    """
    return (
        db.query(models.TableroProduccion)
        .filter(
            models.TableroProduccion.equipo_id == equipo_id,
            models.TableroProduccion.unidad_lectura == unidad,
            models.TableroProduccion.lectura_camion.isnot(None),
        )
        .order_by(models.TableroProduccion.fecha.desc(), models.TableroProduccion.id.desc())
        .first()
    )


def validar_lectura(db, registro, equipo):
    """Valida la lectura del camion y devuelve (lectura, unidad) a persistir.

    - Si el payload no trae lectura, devuelve (None, None): el backend es
      tolerante y guarda NULL.
    - La unidad la resuelve el servidor desde el equipo; el cliente no la manda.
    - Si la lectura es menor a la anterior y no viene permitir_lectura_menor,
      se rechaza con 400 indicando el valor anterior.
    """
    if registro.lectura_camion is None:
        return None, None

    lectura = _decimal("lectura_camion", registro.lectura_camion)
    if lectura <= 0:
        raise HTTPException(status_code=400, detail="La lectura del camion debe ser mayor a 0")

    unidad = unidad_de_equipo(equipo)
    anterior = ultima_lectura(db, equipo.id, unidad)
    if anterior is not None:
        previa = Decimal(str(anterior.lectura_camion))
        if lectura < previa and not registro.permitir_lectura_menor:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"La lectura ({lectura}) no puede ser menor a la ultima registrada "
                    f"({previa}) para este camion"
                ),
            )
    return lectura, unidad
```

- [ ] **Step 5: Persistir la lectura en `_build_record` y `create_trip`**

En `backend/trip_service.py`, `_build_record` cambia su firma para recibir la lectura y la unidad. Reemplazar la firma:

```python
def _build_record(registro, employee, equipo, proveedor_id, cliente_id, weights, lectura=None, unidad=None):
```

Y dentro del `return models.TableroProduccion(...)`, agregar después de `neto_origen=neto_origen, neto_destino=neto_destino, pesaje_unico=registro.pesaje_unico,`:

```python
        lectura_camion=lectura, unidad_lectura=unidad,
```

En `backend/trip_service.py`, `create_trip`, reemplazar:

```python
    proveedor_id, cliente_id = _catalogs(db, registro)
    record = _build_record(
        registro, employee, equipo, proveedor_id, cliente_id, _weights(registro)
    )
```

por:

```python
    proveedor_id, cliente_id = _catalogs(db, registro)
    lectura, unidad = validar_lectura(db, registro, equipo)
    record = _build_record(
        registro, employee, equipo, proveedor_id, cliente_id, _weights(registro), lectura, unidad
    )
```

- [ ] **Step 6: Correr los tests y verificar que pasan**

Run: `py -m pytest backend/test_trip_lectura_camion.py -q`
Expected: PASS (todos)

Si falla `test_lectura_no_numerica_o_no_positiva_es_rechazada` con error de422 en vez de 400, es porque Pydantic valida el tipo antes del servicio: el valor `0` es un `int` válido para `Optional[float]`, así que debe llegar al servicio y devolver 400. Verificar que el test espera 400 y no 422.

- [ ] **Step 7: Exponer la lectura en el historial**

En `backend/main.py`, función `read_historial_viajes`, dentro del `result.append({...})`, agregar después de `"observaciones": tablero.observaciones,`:

```python
            "lectura_camion": float(tablero.lectura_camion) if tablero.lectura_camion is not None else None,
            "unidad_lectura": tablero.unidad_lectura,
```

- [ ] **Step 8: Correr la suite completa del backend**

Run: `py -m pytest backend -q`
Expected: PASS (todas las pruebas existentes siguen pasando)

- [ ] **Step 9: Commit**

```bash
git add backend/schemas.py backend/trip_service.py backend/main.py backend/test_trip_lectura_camion.py
git commit -m "feat(viajes): validar y persistir la lectura del camion en tablero_produccion

- El servidor resuelve la unidad desde equipos.unidad_hr_km y la graba como
  snapshot en unidad_lectura: el cliente no manda la unidad.
- Monotonia contra el ultimo viaje del mismo equipo con la misma unidad.
  permitir_lectura_menor deja pasar una lectura menor (confirmacion del chofer).
- Payload sin lectura se guarda NULL: el backend tolera app vieja y viajes
  offline pendientes."
```

---

### Task 3: Endpoint de última lectura y flag de exigencia

**Files:**
- Modify: `backend/main.py` (nuevo endpoint + `app-version`)
- Test: `backend/test_trip_lectura_camion.py`

**Interfaces:**
- Consumes: `trip_service.unidad_de_equipo`, `trip_service.ultima_lectura` (Task 2).
- Produces:
  - `GET /api/registro-viaje/ultima-lectura?equipo_id=<int>` → `200` con `{"equipo_id": int, "lectura_camion": float|None, "unidad_lectura": str|None, "fecha": str|None}` o `200` con `null`.
  - `GET /api/app-version` → ahora incluye `"exigir_lectura_camion": bool`.
  - `main.EXIGIR_LECTURA_CAMION` — booleano leído de `VIAJE_EXIGIR_LECTURA_CAMION`, default `True`.

- [ ] **Step 1: Escribir el test que falla**

Agregar a `backend/test_trip_lectura_camion.py`:

```python
class LecturaCamionEndpointTest(LecturaCamionBaseTest):
    def test_ultima_lectura_devuelve_la_lectura_del_ultimo_viaje(self):
        self._crear_viaje(lectura_camion=7777, numero_remision="002-003-0000061")

        from fastapi import HTTPException
        from fastapi.testclient import TestClient
        import main

        main.app.dependency_overrides[main.get_db] = lambda: self.db
        main.app.dependency_overrides[main.get_current_user] = lambda: self.empleado
        client = TestClient(main.app)
        try:
            respuesta = client.get("/api/registro-viaje/ultima-lectura", params={"equipo_id": 10})
            self.assertEqual(respuesta.status_code, 200)
            cuerpo = respuesta.json()
            self.assertEqual(cuerpo["equipo_id"], 10)
            self.assertEqual(float(cuerpo["lectura_camion"]), 7777.0)
            self.assertEqual(cuerpo["unidad_lectura"], "km")
        finally:
            main.app.dependency_overrides.clear()

    def test_ultima_lectura_sin_viajes_devuelve_null(self):
        from fastapi.testclient import TestClient
        import main

        main.app.dependency_overrides[main.get_db] = lambda: self.db
        main.app.dependency_overrides[main.get_current_user] = lambda: self.empleado
        client = TestClient(main.app)
        try:
            respuesta = client.get("/api/registro-viaje/ultima-lectura", params={"equipo_id": 10})
            self.assertEqual(respuesta.status_code, 200)
            self.assertIsNone(respuesta.json())
        finally:
            main.app.dependency_overrides.clear()

    def test_app_version_expone_el_flag_de_exigencia(self):
        from fastapi.testclient import TestClient
        import main

        client = TestClient(main.app)
        respuesta = client.get("/api/app-version")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("exigir_lectura_camion", respuesta.json())
        self.assertIsInstance(respuesta.json()["exigir_lectura_camion"], bool)

    def test_flag_por_variable_de_entorno(self):
        import importlib
        import main

        original = os.environ.get("VIAJE_EXIGIR_LECTURA_CAMION")
        try:
            os.environ["VIAJE_EXIGIR_LECTURA_CAMION"] = "false"
            self.assertFalse(main.leer_flag_exigir_lectura_camion())
            os.environ["VIAJE_EXIGIR_LECTURA_CAMION"] = "0"
            self.assertFalse(main.leer_flag_exigir_lectura_camion())
            os.environ["VIAJE_EXIGIR_LECTURA_CAMION"] = "true"
            self.assertTrue(main.leer_flag_exigir_lectura_camion())
            os.environ.pop("VIAJE_EXIGIR_LECTURA_CAMION", None)
            self.assertTrue(main.leer_flag_exigir_lectura_camion())
        finally:
            if original is None:
                os.environ.pop("VIAJE_EXIGIR_LECTURA_CAMION", None)
            else:
                os.environ["VIAJE_EXIGIR_LECTURA_CAMION"] = original
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `py -m pytest backend/test_trip_lectura_camion.py -q -k Endpoint`
Expected: FAIL con 404 en `/api/registro-viaje/ultima-lectura`

- [ ] **Step 3: Implementar el flag y el endpoint**

En `backend/main.py`, agregar la función helper e importarlo de `trip_service`. Reemplazar el import `from trip_service import create_trip` por:

```python
from trip_service import create_trip, ultima_lectura, unidad_de_equipo
```

Agregar la función helper en `backend/main.py`, antes de la sección `# --- Endpoints ---`:

```python
def leer_flag_exigir_lectura_camion() -> bool:
    """Elige si el formulario exige la lectura del camion.

    Variable de entorno VIAJE_EXIGIR_LECTURA_CAMION, default true.
    Permite relajar la exigencia en produccion sin redesplegar.
    """
    valor = os.getenv("VIAJE_EXIGIR_LECTURA_CAMION", "true").strip().lower()
    return valor not in ("0", "false", "no", "off")
```

Agregar el endpoint en `backend/main.py`, después del endpoint `read_historial_viajes`:

```python
@api_router.get("/registro-viaje/ultima-lectura")
def read_ultima_lectura_camion(
    equipo_id: int,
    db: Session = Depends(get_db),
    current_user: models.Empleado = Depends(get_current_user),
):
    equipo = db.query(models.Equipo).filter(models.Equipo.id == equipo_id).first()
    if equipo is None:
        raise HTTPException(status_code=404, detail="Movil no encontrado")

    unidad = unidad_de_equipo(equipo)
    anterior = ultima_lectura(db, equipo_id, unidad)
    if anterior is None:
        return None

    return {
        "equipo_id": equipo_id,
        "lectura_camion": float(anterior.lectura_camion),
        "unidad_lectura": anterior.unidad_lectura,
        "fecha": str(anterior.fecha),
    }
```

En `backend/main.py`, el endpoint `get_app_version`, reemplazar el `return` por:

```python
    return {
        "release": release,
        "deployed_at": deployed_at,
        "exigir_lectura_camion": leer_flag_exigir_lectura_camion(),
    }
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `py -m pytest backend/test_trip_lectura_camion.py -q`
Expected: PASS (todos)

- [ ] **Step 5: Correr la suite completa del backend**

Run: `py -m pytest backend -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/test_trip_lectura_camion.py
git commit -m "feat(api): endpoint de ultima lectura del camion y flag de exigencia

GET /api/registro-viaje/ultima-lectura devuelve la ultima lectura del equipo
con su unidad, o null si todavia no tiene viajes con lectura.

GET /api/app-version expone exigir_lectura_camion, leído de
VIAJE_EXIGIR_LECTURA_CAMION (default true), para que el frontend sepa si el
campo es obligatorio sin desplegar."
```

---

### Task 4: Helpers de frontend y normalización del payload

**Files:**
- Modify: `frontend/src/services/criticalScreens.js`
- Modify: `frontend/src/services/syncPendingRecord.js`
- Test: `frontend/tests/criticalScreens.test.js`, `frontend/tests/syncPendingRecord.test.js`

**Interfaces:**
- Consumes: `normalizePatente`, `findEquipoByPatente` (ya existen en `criticalScreens.js`).
- Produces:
  - `criticalScreens.normalizarLectura(value) -> number` — `NaN` si no es numérico. Acepta `"1.234,5"`, `"1234.5"`, `"1234"`.
  - `criticalScreens.getPendingViajeLastLectura(pendingRecords, patente) -> number | null` — busca por **patente** normalizado, porque un viaje pendiente guarda `patente` y no `equipo_id` (el `equipo_id` lo resuelve el backend a partir de la patente).
  - `criticalScreens.buildViajePayload({ form, userId, lecturaCamion, permitirLecturaMenor }) -> object`
  - `criticalScreens.combineRemito(tipo, sucursal, numero) -> string`
  - `criticalScreens.LECTURA_STORAGE_PREFIX = 'lectura_camion_'` — prefijo de la clave en `localStorage` por equipo.

- [ ] **Step 1: Escribir el test que falla**

Agregar a `frontend/tests/criticalScreens.test.js`, al final del archivo:

```javascript
test('normalizarLectura acepta coma y punto decimales', () => {
  assert.equal(normalizarLectura('1.234,5'), 1234.5)
  assert.equal(normalizarLectura('1234.5'), 1234.5)
  assert.equal(normalizarLectura('1234'), 1234)
  assert.equal(normalizarLectura(1234), 1234)
  assert.ok(Number.isNaN(normalizarLectura('')))
  assert.ok(Number.isNaN(normalizarLectura('abc')))
})

test('getPendingViajeLastLectura toma la lectura pendiente mas reciente del camion', () => {
  const pendientes = [
    { record_type: 'viaje', patente: 'ABC123', lectura_camion: 100, local_id: 1 },
    { record_type: 'viaje', patente: 'ABC123', lectura_camion: 250, local_id: 2 },
    { record_type: 'viaje', patente: 'XYZ789', lectura_camion: 999, local_id: 3 },
    { record_type: 'carreton', patente: 'ABC123', km_final: 5000, local_id: 4 },
  ]

  assert.equal(getPendingViajeLastLectura(pendientes, 'ABC123'), 250)
  assert.equal(getPendingViajeLastLectura(pendientes, 'XYZ789'), 999)
  assert.equal(getPendingViajeLastLectura(pendientes, 'NOPE111'), null)
  assert.equal(getPendingViajeLastLectura([], 'ABC123'), null)
})

test('getPendingViajeLastLectura compara patentes normalizadas', () => {
  const pendientes = [
    { record_type: 'viaje', patente: 'AB 123 CD', lectura_camion: 300, local_id: 1 },
  ]

  assert.equal(getPendingViajeLastLectura(pendientes, 'AB123CD'), 300)
})

test('getPendingViajeLastLectura ignora viajes sin lectura', () => {
  const pendientes = [
    { record_type: 'viaje', patente: 'ABC123', lectura_camion: null, local_id: 1 },
  ]

  assert.equal(getPendingViajeLastLectura(pendientes, 'ABC123'), null)
})

test('buildViajePayload incluye la lectura y el permiso de menor', () => {
  const payload = buildViajePayload({
    form: {
      fecha_remision: '2026-11-09',
      fecha_recepcion: '2026-11-09',
      proveedor_id: 1,
      cliente_id: 2,
      remito_prov_tipo: '002',
      remito_prov_sucursal: '003',
      remito_prov_numero: '0000001',
      remito_fpv_tipo: '002',
      remito_fpv_sucursal: '003',
      remito_fpv_numero: '0000002',
      lote: '',
      peso_bruto_destino: 50,
      tara_destino: 18,
      neto_destino: 32,
      neto_origen: 32,
      chofer_id: 7,
      patente: 'ABC123',
      unidad_negocio_id: 1,
      observaciones: '',
    },
    userId: 7,
    lecturaCamion: '1.234,5',
    permitirLecturaMenor: true,
  })

  assert.equal(payload.lectura_camion, 1234.5)
  assert.equal(payload.permitir_lectura_menor, true)
  assert.equal(payload.numero_remision, '002-003-0000001')
  assert.equal(payload.numero_remision_fpv, '002-003-0000002')
  assert.equal(payload.patente, 'ABC123')
})

test('buildViajePayload omite la lectura cuando no se cargo', () => {
  const payload = buildViajePayload({
    form: { fecha_remision: '2026-11-09', patente: 'ABC123' },
    userId: 7,
    lecturaCamion: '',
    permitirLecturaMenor: false,
  })

  assert.equal('lectura_camion' in payload, false)
  assert.equal(payload.permitir_lectura_menor, false)
})
```

Actualizar el import del principio del archivo `frontend/tests/criticalScreens.test.js`:

```javascript
import {
  FUEL_REMITO_MAX_LENGTH,
  buildCarretonPayload,
  buildFuelLastKmParams,
  buildFuelPayload,
  buildHistoryRequests,
  buildViajePayload,
  findEquipoByPatente,
  findUnidadById,
  getLastFuelKmHora,
  getPendingCarretonLastKm,
  getPendingViajeLastLectura,
  getStoredUserId,
  normalizeKilometraje,
  normalizeFuelRemito,
  normalizeApiList,
  normalizarLectura,
} from '../src/services/criticalScreens.js'
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd frontend; node --test tests/criticalScreens.test.js`
Expected: FAIL con `SyntaxError: The requested module does not provide an export named 'normalizarLectura'`

- [ ] **Step 3: Implementar los helpers**

En `frontend/src/services/criticalScreens.js`, agregar al final del archivo:

```javascript
export const LECTURA_STORAGE_PREFIX = 'lectura_camion_'

export const normalizarLectura = (value) => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : NaN

  const raw = String(value ?? '').trim()
  if (!raw) return NaN

  const compact = raw.replace(/\s+/g, '')

  if (compact.includes(',') && compact.includes('.')) {
    return Number(compact.replace(/\./g, '').replace(',', '.'))
  }

  if (compact.includes(',')) {
    return Number(compact.replace(',', '.'))
  }

  if (/^\d{1,3}(\.\d{3})+$/.test(compact)) {
    return Number(compact.replace(/\./g, ''))
  }

  return Number(compact)
}

export const getPendingViajeLastLectura = (pendingRecords, patente) => {
  const target = normalizePatente(patente)
  if (!target) return null

  const sameCamion = (pendingRecords || [])
    .filter((record) => (record.record_type || 'viaje') === 'viaje'
      && normalizePatente(record.patente) === target
      && record.lectura_camion !== undefined
      && record.lectura_camion !== null
      && record.lectura_camion !== '')
    .sort((left, right) => (left.local_id || 0) - (right.local_id || 0))

  if (sameCamion.length === 0) return null

  const value = normalizarLectura(sameCamion[sameCamion.length - 1].lectura_camion)
  return Number.isFinite(value) ? value : null
}

export const buildViajePayload = ({ form, userId, lecturaCamion, permitirLecturaMenor }) => {
  const payload = {
    fecha_remision: form.fecha_remision,
    fecha_recepcion: form.fecha_recepcion,
    proveedor_id: form.proveedor_id,
    cliente_id: form.cliente_id,
    numero_remision: combineRemito(form.remito_prov_tipo, form.remito_prov_sucursal, form.remito_prov_numero),
    numero_remision_fpv: combineRemito(form.remito_fpv_tipo, form.remito_fpv_sucursal, form.remito_fpv_numero),
    lote: form.lote,
    peso_bruto_destino: Number(form.peso_bruto_destino),
    tara_destino: Number(form.tara_destino),
    neto_destino: Number(form.neto_destino),
    neto_origen: Number(form.neto_origen),
    chofer_id: Number(form.chofer_id || userId),
    patente: form.patente,
    unidad_negocio_id: Number(form.unidad_negocio_id || 1),
    observaciones: form.observaciones,
    permitir_lectura_menor: Boolean(permitirLecturaMenor),
  }

  const lectura = normalizarLectura(lecturaCamion)
  if (Number.isFinite(lectura) && lectura > 0) {
    payload.lectura_camion = lectura
  }

  return payload
}
```

El helper `combineRemito` no existe todavía en `criticalScreens.js`: agregarlo junto con los anteriores:

```javascript
const padZeros = (value, length) => String(value || '').padStart(length, '0')

export const combineRemito = (tipo, sucursal, numero) => {
  if (!tipo && !sucursal && !numero) return ''
  const t = padZeros(tipo, 3)
  const s = padZeros(sucursal, 3)
  const n = padZeros(numero, 7)
  return `${t}-${s}-${n}`
}
```

`NewTrip.vue` ya tiene un `combineRemito` local idéntico (`frontend/src/views/NewTrip.vue:105-111`). En el Step 6 de la Task 5 se reemplaza por el import compartido, para que la regla de padding de los remitos viva en un solo lugar.

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd frontend; node --test tests/criticalScreens.test.js`
Expected: PASS (todos)

- [ ] **Step 5: Normalizar la lectura en el payload de sincronización**

En `frontend/src/services/syncPendingRecord.js`, en `preparePendingPayload`, después de la línea `if (payload.neto_destino) payload.neto_destino = Number(payload.neto_destino)`, agregar:

```javascript
  if (payload.lectura_camion !== undefined && payload.lectura_camion !== null && payload.lectura_camion !== '') {
    payload.lectura_camion = Number(payload.lectura_camion)
  } else {
    delete payload.lectura_camion
  }
```

- [ ] **Step 6: Escribir el test del payload de sincronización**

Agregar a `frontend/tests/syncPendingRecord.test.js`:

```javascript
test('preparePendingPayload convierte la lectura en numero', () => {
  const { payload } = preparePendingPayload({
    record_type: 'viaje',
    patente: 'ABC123',
    lectura_camion: '1234.5',
    permitir_lectura_menor: true,
  }, { clientLogger: { userId: 7 } })

  assert.equal(payload.lectura_camion, 1234.5)
  assert.equal(payload.permitir_lectura_menor, true)
})

test('preparePendingPayload omite la lectura vacia', () => {
  const { payload } = preparePendingPayload({
    record_type: 'viaje',
    patente: 'ABC123',
    lectura_camion: '',
  }, { clientLogger: { userId: 7 } })

  assert.equal('lectura_camion' in payload, false)
})
```

Si el archivo no importa `preparePendingPayload`, agregarlo al import existente.

- [ ] **Step 7: Correr los tests y verificar que pasan**

Run: `cd frontend; node --test tests/syncPendingRecord.test.js tests/criticalScreens.test.js`
Expected: PASS (todos)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/services/criticalScreens.js frontend/src/services/syncPendingRecord.js frontend/tests/criticalScreens.test.js frontend/tests/syncPendingRecord.test.js
git commit -m "feat(frontend): helpers de lectura del camion y payload normalizado

Agrega normalizarLectura, getPendingViajeLastLectura y buildViajePayload a
criticalScreens.js, y normaliza lectura_camion en el payload de sincronizacion
para que llegue como numero al backend."
```

---

### Task 5: Campo de lectura en la pantalla de registro de viajes

**Files:**
- Modify: `frontend/src/views/NewTrip.vue`
- Test: `frontend/tests/newTripLectura.test.js` (nuevo)

**Interfaces:**
- Consumes: `normalizarLectura`, `getPendingViajeLastLectura`, `buildViajePayload`, `findEquipoByPatente`, `LECTURA_STORAGE_PREFIX` (Task 4); `GET /api/registro-viaje/ultima-lectura` y `GET /api/app-version` (Task 3).
- Produces: el formulario "Nuevo Registro" muestra el campo de lectura con la unidad del camión.

- [ ] **Step 1: Escribir el test que falla**

Crear `frontend/tests/newTripLectura.test.js`:

```javascript
import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(here, '..', 'src', 'views', 'NewTrip.vue'), 'utf8')

test('el formulario de nuevo viaje muestra el campo de lectura con la unidad', () => {
  assert.match(source, /v-model="form\.lectura_camion"/)
  assert.match(source, /Lectura/)
})

test('el formulario consulta la ultima lectura del camion', () => {
  assert.match(source, /registro-viaje\/ultima-lectura/)
})

test('el formulario bloquea el envio si falta la lectura cuando el flag esta activo', () => {
  assert.match(source, /exigir_lectura_camion/)
  assert.match(source, /lectura_camion/)
})

test('el formulario pide confirmacion cuando la lectura es menor a la anterior', () => {
  assert.match(source, /permitir_lectura_menor/)
})
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd frontend; node --test tests/newTripLectura.test.js`
Expected: FAIL (no encuentra `v-model="form.lectura_camion"`)

- [ ] **Step 3: Agregar el estado al formulario**

En `frontend/src/views/NewTrip.vue`, en el `<script setup>`, agregar los imports:

```javascript
import { findEquipoByPatente, buildViajePayload, combineRemito, getPendingViajeLastLectura, normalizarLectura, LECTURA_STORAGE_PREFIX } from '../services/criticalScreens.js';
```

Y borrar el `combineRemito` local del view (`frontend/src/views/NewTrip.vue:105-111`), dejando el import compartido como unica fuente. El `padZeros` local (`NewTrip.vue:89-91`) **se queda**: lo usan `onRemitoPadTipo`, `onRemitoPadSucursal` y `onRemitoPadNumero`, que el template sigue invocando.

Después de `const sync = useSyncStore();`, agregar:

```javascript
const exigirLecturaCamion = ref(true);
const ultimaLectura = ref(null);
const cargandoUltimaLectura = ref(false);
```

En el `form` de `ref({...})`, agregar `lectura_camion: ''` después de `patente: '',`:

```javascript
    patente: '',
    lectura_camion: '',
```

Después del bloque `const form = ref({...});`, agregar el computed de la unidad. Va **después** del `form` porque lo consulta:

```javascript
// La unidad la define el admin por camion (equipos.unidad_hr_km) y llega en el
// catalogo de equipos. Solo se usa para etiquetar el campo.
const unidadLecturaLabel = computed(() => {
    const equipo = findEquipoByPatente(catalog.equipos, form.value.patente);
    return equipo && equipo.unidad_hr_km === 'hs' ? 'horas' : 'km';
});
```

- [ ] **Step 4: Cargar la última lectura al montar**

En `frontend/src/views/NewTrip.vue`, agregar las funciones `applyUltimaLectura` y `fetchUltimaLectura` antes de `onMounted`:

```javascript
const applyUltimaLectura = (value) => {
    if (value === null || value === undefined) {
        ultimaLectura.value = null;
        return;
    }
    const lectura = Number(value.lectura_camion);
    if (!Number.isFinite(lectura)) {
        ultimaLectura.value = null;
        return;
    }
    ultimaLectura.value = {
        lectura: lectura,
        unidad: value.unidad_lectura || 'km',
        fecha: value.fecha || null
    };
};

const fetchUltimaLectura = async (equipoId) => {
    if (!equipoId) {
        ultimaLectura.value = null;
        return;
    }

    const storageKey = `${LECTURA_STORAGE_PREFIX}${equipoId}`;
    const pendingLectura = getPendingViajeLastLectura(sync.pendingRecords, form.value.patente);
    if (pendingLectura !== null) {
        applyUltimaLectura({ lectura_camion: pendingLectura, unidad_lectura: unidadLecturaLabel.value === 'horas' ? 'hs' : 'km' });
        return;
    }

    cargandoUltimaLectura.value = true;
    try {
        const response = await axios.get(`${API_URL}/registro-viaje/ultima-lectura`, {
            params: { equipo_id: Number(equipoId) }
        });
        applyUltimaLectura(response.data);
        if (response.data && response.data.lectura_camion !== null) {
            localStorage.setItem(storageKey, String(response.data.lectura_camion));
        }
    } catch (error) {
        const cached = localStorage.getItem(storageKey);
        if (cached !== null) {
            applyUltimaLectura({ lectura_camion: Number(cached), unidad_lectura: unidadLecturaLabel.value === 'horas' ? 'hs' : 'km' });
        } else {
            ultimaLectura.value = null;
        }
    } finally {
        cargandoUltimaLectura.value = false;
    }
};
```

En `onMounted`, después de `await catalog.fetchCatalogues();`, agregar:

```javascript
    try {
        const versionRes = await axios.get(`${API_URL}/app-version`);
        exigirLecturaCamion.value = versionRes.data?.exigir_lectura_camion !== false;
    } catch (error) {
        exigirLecturaCamion.value = true;
    }
```

Y al final del `onMounted`, después del bloque que setea `default_unidad_negocio`, agregar:

```javascript
    const equipo = findEquipoByPatente(catalog.equipos, form.value.patente);
    if (equipo) {
        await fetchUltimaLectura(equipo.id);
    }
```

- [ ] **Step 5: Validar y enviar la lectura**

En `frontend/src/views/NewTrip.vue`, en `submitForm`, después del bloque de validación de `faltantes` (el que empieza con `if ((needProveedor && !form.value.proveedor_id) ...`), agregar:

```javascript
    const lecturaValor = normalizarLectura(form.value.lectura_camion);
    const lecturaValida = Number.isFinite(lecturaValor) && lecturaValor > 0;

    if (exigirLecturaCamion.value && !lecturaValida) {
        Swal.fire({
            icon: 'warning',
            title: 'Faltan datos',
            text: 'Complete la lectura de km/horas del camion',
            confirmButtonColor: '#007AFF'
        });
        return;
    }

    let permitirLecturaMenor = false;
    if (lecturaValida && ultimaLectura.value && lecturaValor < ultimaLectura.value.lectura) {
        const confirmacion = await Swal.fire({
            icon: 'warning',
            title: 'Lectura menor que la anterior',
            html: `La lectura (${lecturaValor}) es menor a la ultima registrada (${ultimaLectura.value.lectura}).<br>¿Desea continuar y guardar el registro igual?`,
            showCancelButton: true,
            confirmButtonText: 'Guardar igual',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#d97706'
        });
        if (!confirmacion.isConfirmed) {
            return;
        }
        permitirLecturaMenor = true;
    }
```

Y reemplazar el bloque `const result = await sync.saveRecord({...form.value, numero_remision, numero_remision_fpv}, 'viaje');` por:

```javascript
        const result = await sync.saveRecord(buildViajePayload({
            form: form.value,
            userId: form.value.chofer_id,
            lecturaCamion: lecturaValor,
            permitirLecturaMenor: permitirLecturaMenor
        }), 'viaje');
```

Nota: `buildViajePayload` ya calcula `numero_remision` y `numero_remision_fpv` con `combineRemito`, así que las variables locales `numero_remision` y `numero_remision_fpv` que se calculan más arriba se siguen usando para la validación de duplicados. No eliminarlas.

- [ ] **Step 6: Agregar el campo al template**

En `frontend/src/views/NewTrip.vue`, en el `<template>`, después del bloque de la `Patente` (el `<div>` que cierra con "Se configura desde Ajustes"), agregar:

```html
        <div>
            <label class="block text-xs font-medium text-gray-500 mb-1">
                Lectura del camion ({{ unidadLecturaLabel }}) <span v-if="exigirLecturaCamion" class="text-red-500">*</span>
            </label>
            <input
                v-model="form.lectura_camion"
                type="number"
                step="0.01"
                min="0"
                inputmode="decimal"
                class="w-full p-2 rounded border dark:bg-gray-800 dark:border-gray-700 dark:text-white"
                placeholder="Odometro actual">
            <div v-if="cargandoUltimaLectura" class="text-xs text-gray-400 mt-1">Buscando ultima lectura...</div>
            <div v-else-if="ultimaLectura" class="text-xs text-gray-400 mt-1">
                Ultima lectura: {{ ultimaLectura.lectura.toFixed(2) }} {{ ultimaLectura.unidad }}
            </div>
            <div v-else class="text-xs text-gray-400 mt-1">Aun no hay lecturas registradas para este camion.</div>
        </div>
```

(El computed `unidadLecturaLabel` ya se agrego en el Step 3, despues del `form`.)

- [ ] **Step 7: Correr el test y verificar que pasa**

Run: `cd frontend; node --test tests/newTripLectura.test.js`
Expected: PASS (4 tests)

- [ ] **Step 8: Correr toda la suite del frontend**

Run: `cd frontend; npm run verify`
Expected: PASS (tests + build)

- [ ] **Step 9: Commit**

```bash
git add frontend/src/views/NewTrip.vue frontend/tests/newTripLectura.test.js
git commit -m "feat(viajes): campo de lectura del camion en el registro de viajes

Muestra la lectura con la unidad del camion (km o hs), precarga la ultima
lectura conocida, avisa cuando es menor a la anterior y deja al chofer
confirmar con 'Guardar igual' (-> permitir_lectura_menor).

El campo es obligatorio cuando exigir_lectura_camion esta activo."
```

---

### Task 6: Mostrar la lectura en el historial y documentar

**Files:**
- Modify: `frontend/src/views/History.vue`
- Modify: `README.md`
- Test: `frontend/tests/newTripLectura.test.js` (extender)

**Interfaces:**
- Consumes: `HistorialViajeItem.lectura_camion` / `.unidad_lectura` (Task 2).
- Produces: el historial muestra la lectura de cada viaje; el README documenta la migración y el flag.

- [ ] **Step 1: Escribir el test que falla**

Agregar a `frontend/tests/newTripLectura.test.js`:

```javascript
test('el historial muestra la lectura de cada viaje', () => {
  const history = readFileSync(join(here, '..', 'src', 'views', 'History.vue'), 'utf8')
  assert.match(history, /item\.lectura_camion/)
  assert.match(history, /item\.unidad_lectura/)
})
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd frontend; node --test tests/newTripLectura.test.js`
Expected: FAIL (no encuentra `item.lectura_camion`)

- [ ] **Step 3: Mostrar la lectura en el historial**

En `frontend/src/views/History.vue`, en el bloque de cada viaje del historial (después del `<div v-if="item.observaciones" ...>`), agregar:

```html
            <div v-if="item.lectura_camion !== null && item.lectura_camion !== undefined" class="text-xs text-gray-400 mt-1">
                Lectura: {{ Number(item.lectura_camion).toFixed(2) }} {{ item.unidad_lectura === 'hs' ? 'hs' : 'km' }}
            </div>
```

- [ ] **Step 4: Documentar en el README**

En `README.md`, agregar una sección nueva después de la sección "### Carga de viajes desde imagen (OCR)", con el título `### Lectura de km/horas del camion en los viajes`:

````markdown
### Lectura de km/horas del camion en los viajes

El formulario **Nuevo Registro** pide la lectura del odometro (km) o del
horometro (horas) del camion y la guarda en `tablero_produccion.lectura_camion`,
con la unidad en `unidad_lectura`.

- La unidad es **fija por camion** y la define el admin en `equipos.unidad_hr_km`
  (`'km'` o `'hs'`). El cliente nunca manda la unidad: el backend la resuelve
  desde el equipo y la graba como snapshot, asi corregir la unidad de un camion
  no reescribe los viajes historicos.
- `lectura_camion` es nullable: `NULL` significa "sin lectura registrada".
- La referencia de monotonía es el ultimo viaje del mismo equipo **con la misma
  unidad**. Si el admin cambia la unidad, la comparacion se desactiva en vez de
  comparar numeros sin sentido.
- Si la lectura es menor a la anterior, el backend la rechaza con 400. El chofer
  puede confirmar con "Guardar igual", que viaja como `permitir_lectura_menor`.
- El backend **tolera** el payload sin `lectura_camion`: se guarda `NULL`. Esto
  cubre la app vieja y los viajes offline pendientes de la version anterior.

#### Interruptor

`VIAJE_EXIGIR_LECTURA_CAMION` (default `true`) gobierna si el formulario exige la
lectura. Con `false` el campo pasa a opcional, para el caso de un camion que no
reporta odometro. El valor viaja en `GET /api/app-version` como
`exigir_lectura_camion`, y el frontend lo cachea para funcionar offline.

```bash
VIAJE_EXIGIR_LECTURA_CAMION=true
```

#### Migracion MySQL

**Aplicar la migracion ANTES de desplegar el backend.** El backend nuevo
selecciona `lectura_camion` y `unidad_lectura` en cada viaje y falla con
`OperationalError` si las columnas no existen.

```bash
set -Eeuo pipefail
umask 077

: "${DB_NAME:?Definir DB_NAME}"
: "${MYSQL_CNF:?Definir MYSQL_CNF con ruta absoluta}"
: "${BACKUP_DIR:?Definir BACKUP_DIR con ruta absoluta}"
[[ "$DB_NAME" =~ ^[A-Za-z0-9_]+$ ]]
[[ "$MYSQL_CNF" = /* && -r "$MYSQL_CNF" ]]
[[ "$BACKUP_DIR" = /* ]]
install -d -m 0700 -- "$BACKUP_DIR"

BACKUP="$(mktemp --tmpdir="$BACKUP_DIR" "pre-lectura-camion-${DB_NAME}-$(date +%Y%m%d-%H%M%S)-XXXXXX.sql")"
cleanup_pre_migration() {
    status=$?; trap - ERR INT TERM HUP
    rm -f -- "$BACKUP"
    (( status != 0 )) || status=1
    exit "$status"
}
trap cleanup_pre_migration ERR INT TERM HUP

mysqldump --defaults-extra-file="$MYSQL_CNF" --single-transaction --routines --triggers --events --databases "$DB_NAME" > "$BACKUP"
[[ -s "$BACKUP" ]]
sync -f "$BACKUP"
trap - ERR INT TERM HUP

mysql --defaults-extra-file="$MYSQL_CNF" "$DB_NAME" < backend/migrations/20261109_add_lectura_camion.sql
mysql --defaults-extra-file="$MYSQL_CNF" --table "$DB_NAME" < backend/migrations/20261109_verify_lectura_camion.sql
printf 'Backup previo: %s\n' "$BACKUP"
```

La migracion es idempotente. La verificacion es de solo lectura y debe mostrar:

- `tablero_produccion.lectura_camion` nullable DECIMAL;
- `tablero_produccion.unidad_lectura` nullable VARCHAR(3);
- `equipos.unidad_hr_km` NOT NULL con default `km`;
- cero filas con lectura no nula y cero equipos con unidad invalida.

#### Configurar la unidad de un camion

No hay pantalla de administracion de equipos: se ajusta por SQL.

```sql
UPDATE equipos SET unidad_hr_km = 'hs' WHERE id = 12;
UPDATE equipos SET unidad_hr_km = 'km' WHERE id = 13;
```

#### Verificacion

```powershell
py -m pytest backend/test_trip_lectura_camion.py -q
py -m pytest backend -q
Set-Location frontend
npm run verify
```
````

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `cd frontend; node --test tests/newTripLectura.test.js`
Expected: PASS (5 tests)

- [ ] **Step 6: Correr la verificación completa**

Run: `py -m pytest backend -q`
Expected: PASS

Run: `cd frontend; npm run verify`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/History.vue frontend/tests/newTripLectura.test.js README.md
git commit -m "feat(historial): mostrar la lectura del camion y documentar la migracion

El historial muestra la lectura de cada viaje con su unidad. El README
documenta el interruptor VIAJE_EXIGIR_LECTURA_CAMION, el orden obligatorio
migracion -> deploy, el ritual de backup y como setear la unidad por camion."
```

---

### Task 7: Verificación final y publicación

**Files:**
- Modify: ninguno (solo verificación y publicación)

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: PR actualizado con la implementación completa.

- [ ] **Step 1: Correr la verificación completa del backend**

Run: `py -m pytest backend -q`
Expected: PASS, sin tests omitidos.

- [ ] **Step 2: Correr la verificación completa del frontend**

Run: `cd frontend; npm run verify`
Expected: PASS (tests + build).

- [ ] **Step 3: Verificar que la suite cubre los casos del spec**

Run: `py -m pytest backend/test_trip_lectura_camion.py -v`
Expected: PASS con los casos: guarda con unidad resuelta, equipo hs, payload ausente, lectura menor rechazada, lectura menor con permiso, lectura no positiva rechazada, no compara entre unidades, no compara con carretón, endpoint de última lectura, app-version con el flag.

- [ ] **Step 4: Confirmar que la rama está limpia**

Run: `git status --short`
Expected: sin salida (todo commiteado).

- [ ] **Step 5: Actualizar el PR**

```bash
git push
gh pr edit 44 --title "feat: lectura de km/horas del camion en tablero_produccion" --body "Implementa la especificacion de docs/superpowers/specs/2026-11-09-lectura-camion-tablero-produccion-design.md.

- lectura_camion DECIMAL nullable + unidad_lectura snapshot en tablero_produccion
- unidad_hr_km en equipos: la unidad es fija por camion y la resuelve el servidor
- Monotonia contra el ultimo viaje del mismo equipo con la misma unidad, con
  override permit_lectura_menor
- Backend tolerante con el payload ausente; la obligatoriedad vive en el
  frontend, gobernada por VIAJE_EXIGIR_LECTURA_CAMION
- Migracion idempotente que debe aplicarse ANTES del deploy del backend
- El flujo OCR y el de carreton quedan intactos"
```

- [ ] **Step 6: Verificar que el PR quedó abierto con los commits**

Run: `gh pr view 44`
Expected: estado OPEN, con el commit del spec y los de implementación.

**Nota de despliegue (no ejecutar sin el operador):** la migración
`backend/migrations/20261109_add_lectura_camion.sql` debe correr en producción
antes del deploy del backend, con el ritual de backup documentado en el README.
La base de producción (`srv1723.hstgr.io`) rechaza conexiones desde la red de
desarrollo por allowlist de IP, así que la aplica el operador en el servidor.
