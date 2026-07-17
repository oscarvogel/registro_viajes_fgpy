# Cliente y Proveedor Obligatorios en OCR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corregir la precarga OCR para proponer Alcogreen como cliente y Forestal Paraguay como proveedor, y exigir la selección de ambas entidades activas antes de confirmar un viaje.

**Architecture:** El adaptador OCR extraerá por separado destinatario y remitente. El backend normalizará y resolverá cada razón social contra su catálogo activo, devolverá ambos candidatos e IDs y volverá a validar los IDs al confirmar. El frontend mostrará dos selectores obligatorios y construirá el payload únicamente cuando ambos valores pertenezcan a los catálogos activos.

**Tech Stack:** Python 3, FastAPI, Pydantic, SQLAlchemy, pytest/unittest, Vue 3, Pinia, Vitest, Node test runner.

---

## Mapa de archivos

- `backend/minimax_vision.py`: contrato estricto y prompt del proveedor OCR.
- `backend/trip_image_normalization.py`: normalización determinista compartida de razones sociales.
- `backend/trip_image_service.py`: resolución independiente de cliente/proveedor y confirmación transaccional.
- `backend/trip_service.py`: validación autoritativa de catálogos para pesaje único.
- `backend/schemas.py`: contratos HTTP de propuesta y confirmación.
- `backend/test_minimax_vision.py`: pruebas del prompt y del objeto JSON aceptado.
- `backend/test_trip_image_normalization.py`: pruebas de normalización de ambas razones sociales.
- `backend/test_trip_image_api.py`: pruebas de resolución, persistencia, rechazo e idempotencia.
- `frontend/src/services/tripImageReview.js`: catálogo activo, modelo de revisión y payload.
- `frontend/src/views/TripImageUpload.vue`: selectores obligatorios de cliente y proveedor.
- `frontend/tests/tripImage.test.js`: pruebas unitarias del modelo y payload.
- `frontend/tests/tripImageUpload.spec.js`: pruebas de interacción de la pantalla.
- `README.md`: comportamiento operativo actualizado y verificación manual.

No se crea una migración: `cliente_id` y `proveedor_id` ya existen en `tablero_produccion`, y ambos catálogos ya se sincronizan al frontend.

### Task 1: Separar cliente y proveedor en el contrato OCR

**Files:**
- Modify: `backend/minimax_vision.py:28-51`
- Modify: `backend/test_minimax_vision.py:15-40`
- Modify: `backend/test_minimax_vision.py:100-111`

- [ ] **Step 1: Cambiar el fixture para exigir ambos candidatos**

En `backend/test_minimax_vision.py`, agregar `cliente_candidato` al objeto válido y mantener `proveedor_candidato`:

```python
VALID = {
    "fecha_remision": "2026-07-13",
    "fecha_remito": "2026-07-13",
    "fecha_ticket": "2026-07-13",
    "remito_tipo": "001",
    "remito_sucursal": "002",
    "remito_numero": "0000123",
    "cliente_candidato": "Alcogreen S.A.",
    "proveedor_candidato": "Forestal Paraguay S.A.",
    "peso_bruto": "49.690,00",
    "tara": "17.080,00",
    "neto": "32.610,00",
    "unidad_peso": "kg",
    "patente_observada": "ABC123",
    "chofer_observado": "Persona",
    "confidence": {
        "fecha_remision": 0.9,
        "fecha_remito": 0.9,
        "fecha_ticket": 0.8,
        "cliente_candidato": 0.9,
        "proveedor_candidato": 0.9,
        "remito_numero": 0.8,
    },
    "warnings": [],
}
```

En la prueba del prompt, exigir las instrucciones de identidad correctas:

```python
def test_prompt_separates_destination_client_from_sender_provider(self):
    self.assertIn("cliente_candidato", PROMPT)
    self.assertIn("proveedor_candidato", PROMPT)
    self.assertIn("DESTINATARIO DE LA MERCADERIA", PROMPT)
    self.assertIn("REMITENTE DE LA MERCADERIA", PROMPT)
    self.assertIn("cliente_candidato toma la razon social de DESTINATARIO", PROMPT)
    self.assertIn("proveedor_candidato toma la razon social de REMITENTE", PROMPT)
```

Agregar una prueba que demuestre que falta una clave contractual:

```python
def test_response_without_client_candidate_is_rejected(self):
    invalid = dict(VALID)
    invalid.pop("cliente_candidato")
    with self.assertRaises(MiniMaxVisionError):
        self.client(FakeExecutor(tool_response(invalid))).analyze(self.image)
```

- [ ] **Step 2: Ejecutar el test y verificar que falle**

Run:

```powershell
py -m pytest backend/test_minimax_vision.py -q
```

Expected: `FAIL`; el prompt y `_REQUIRED` todavía no incluyen `cliente_candidato`.

- [ ] **Step 3: Actualizar el prompt y el validador estricto**

En `backend/minimax_vision.py`, reemplazar el bloque de identidad del prompt por:

```python
PROMPT = """Analiza la imagen para precargar un viaje. Devuelve EXCLUSIVAMENTE un unico objeto JSON,
sin prosa ni markdown, con estas claves exactas: fecha_remision; fecha_remito; fecha_ticket;
remito_tipo; remito_sucursal; remito_numero; cliente_candidato; proveedor_candidato; peso_bruto;
tara; neto; unidad_peso; patente_observada; chofer_observado; confidence (objeto por campo,
solo para las claves de datos anteriores y con valores entre 0 y 1); warnings (array de textos).
Usa null cuando un dato no sea visible. Conserva los pesos y su unidad tal como se observan.
Para la fecha, fecha_remito debe salir de la NOTA DE REMISION/remito principal (Fecha de Emision,
Fecha de expedicion o Fecha de inicio del traslado). fecha_ticket debe salir del ticket de balanza,
especialmente del campo FECHA SALIDA. En fecha_remision priorizar fecha_remito si es visible y legible;
si fecha_remito no esta visible o no es legible, usar fecha_ticket. No uses la fecha actual.
Para cliente_candidato toma la razon social de DESTINATARIO DE LA MERCADERIA.
Para proveedor_candidato toma la razon social de REMITENTE DE LA MERCADERIA.
No intercambies destinatario y remitente. En un numero como 002-003-0003677,
remito_tipo son los primeros 3 digitos (002), remito_sucursal los siguientes 3 (003) y
remito_numero los ultimos 7 (0003677); devuelve solo digitos en cada parte.
Devuelve cada peso como texto copiando todos los digitos y separadores impresos, sin convertirlo
ni reinterpretarlo: si el ticket muestra 49.690,00 kg devuelve "49.690,00", nunca 49.69.
OCR no elige cliente, proveedor, chofer, patente ni unidad: solo informa texto observado.
No normalices datos de negocio ni inventes valores."""
```

Actualizar los conjuntos contractuales:

```python
_REQUIRED = {
    "fecha_remision", "fecha_remito", "fecha_ticket",
    "remito_tipo", "remito_sucursal", "remito_numero",
    "cliente_candidato", "proveedor_candidato",
    "peso_bruto", "tara", "neto", "unidad_peso",
    "patente_observada", "chofer_observado", "confidence", "warnings",
}
_TEXT_FIELDS = {
    "fecha_remision", "fecha_remito", "fecha_ticket",
    "remito_tipo", "remito_sucursal", "remito_numero",
    "cliente_candidato", "proveedor_candidato",
    "unidad_peso", "patente_observada", "chofer_observado",
}
```

`_CONFIDENCE_FIELDS = _TEXT_FIELDS | _WEIGHT_FIELDS` continuará incorporando ambos campos sin lógica adicional.

- [ ] **Step 4: Ejecutar el test y verificar que pase**

Run:

```powershell
py -m pytest backend/test_minimax_vision.py -q
```

Expected: `PASS`.

- [ ] **Step 5: Commit del contrato OCR**

```powershell
git add backend/minimax_vision.py backend/test_minimax_vision.py
git commit -m "fix: separar cliente y proveedor en OCR"
```

### Task 2: Normalizar ambas razones sociales

**Files:**
- Modify: `backend/trip_image_normalization.py:16-29`
- Modify: `backend/trip_image_normalization.py:32-57`
- Modify: `backend/trip_image_normalization.py:134-166`
- Modify: `backend/test_trip_image_normalization.py:17-38`
- Modify: `backend/test_trip_image_normalization.py:220-230`

- [ ] **Step 1: Escribir las pruebas de normalización compartida**

En el fixture principal de `backend/test_trip_image_normalization.py`, usar:

```python
self.data = {
    "fecha_remision": "2026-07-17",
    "remito_tipo": "2",
    "remito_sucursal": "3",
    "remito_numero": "3755",
    "cliente_candidato": "ALCOGREEN S.A.",
    "proveedor_candidato": "FORESTAL PARAGUAY S.A.",
    "peso_bruto": "48.250,00",
    "tara": "16.460,00",
    "neto": "31.790,00",
    "unidad_peso": "kg",
}
```

Actualizar el test principal:

```python
def test_normalizes_reference_document(self):
    result = normalize_extraction(self.data)
    self.assertEqual(result.numero_remision_fpv, "002-003-0003755")
    self.assertEqual(result.cliente_normalizado, "alcogreen")
    self.assertEqual(result.proveedor_normalizado, "forestal paraguay")
    self.assertEqual(result.peso_bruto_destino, Decimal("48.250"))
    self.assertEqual(result.tara_destino, Decimal("16.460"))
    self.assertEqual(result.neto_destino, Decimal("31.790"))
```

Reemplazar la prueba específica de proveedor por una prueba común:

```python
def test_normalizes_business_name_for_clients_and_providers(self):
    expected = {
        "Alcogreen S.A.": "alcogreen",
        "  ÁLCOGREEN,   S A  ": "alcogreen",
        "Alcogreen S.A.S.": "alcogreen",
        "Forestal Paraguay S.A.": "forestal paraguay",
        "FORESTAL PARAGUAY SAIC": "forestal paraguay",
    }
    for value, normalized in expected.items():
        with self.subTest(value=value):
            self.assertEqual(normalize_business_name(value), normalized)
```

- [ ] **Step 2: Ejecutar el test y verificar que falle**

Run:

```powershell
py -m pytest backend/test_trip_image_normalization.py -q
```

Expected: `FAIL`; no existen `cliente_normalizado` ni `normalize_business_name`.

- [ ] **Step 3: Generalizar la normalización y ampliar el resultado**

En `backend/trip_image_normalization.py`, reemplazar la función específica:

```python
def normalize_business_name(value: Any) -> str:
    """Return a comparison key for an OCR business name."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value).lower())
    text = "".join(character for character in text if not unicodedata.combining(character))
    tokens = re.sub(r"[^a-z0-9]+", " ", text).split()
    suffixes = (
        ("s", "a", "i", "c"),
        ("s", "r", "l"),
        ("s", "a", "s"),
        ("s", "a"),
        ("saic",),
        ("srl",),
        ("sas",),
        ("sa",),
    )
    removed = True
    while removed:
        removed = False
        for suffix in suffixes:
            if tuple(tokens[-len(suffix):]) == suffix:
                del tokens[-len(suffix):]
                removed = True
                break
    return " ".join(tokens)
```

Actualizar el dataclass:

```python
@dataclass(frozen=True)
class NormalizedExtraction:
    fecha_remision: date
    numero_remision_fpv: str
    peso_bruto_destino: Decimal
    tara_destino: Decimal
    neto_destino: Decimal
    cliente_normalizado: str
    proveedor_normalizado: str
```

En el retorno de `normalize_extraction`, establecer:

```python
return NormalizedExtraction(
    fecha_remision=_first_valid_date(
        data.get("fecha_remito"),
        data.get("fecha_remision"),
        data.get("fecha_ticket"),
    ),
    numero_remision_fpv=_normalize_remito(data),
    peso_bruto_destino=bruto,
    tara_destino=tara,
    neto_destino=neto,
    cliente_normalizado=normalize_business_name(data.get("cliente_candidato")),
    proveedor_normalizado=normalize_business_name(data.get("proveedor_candidato")),
)
```

Actualizar los imports que todavía usen `normalize_provider_name` para que apunten a `normalize_business_name`.

- [ ] **Step 4: Ejecutar el test y verificar que pase**

Run:

```powershell
py -m pytest backend/test_trip_image_normalization.py -q
```

Expected: `PASS`.

- [ ] **Step 5: Commit de normalización**

```powershell
git add backend/trip_image_normalization.py backend/test_trip_image_normalization.py
git commit -m "refactor: compartir normalizacion de razones sociales"
```

### Task 3: Resolver cliente y proveedor por separado durante el análisis

**Files:**
- Modify: `backend/schemas.py:159-185`
- Modify: `backend/trip_image_service.py:11-50`
- Modify: `backend/test_trip_image_api.py:397-436`

- [ ] **Step 1: Escribir pruebas de resolución única, ambigua y ausente**

En `backend/test_trip_image_api.py`, reemplazar la prueba de resolución por una que cree ambos catálogos:

```python
def test_analysis_resolves_unique_active_client_and_provider(self):
    from image_storage import ImageStorage
    from trip_image_service import TripImageService
    import models

    root = tempfile.TemporaryDirectory()
    self.addCleanup(root.cleanup)
    storage = ImageStorage(Path(root.name).resolve(), "x" * 32)
    vision_data = {
        "fecha_remision": "2026-07-17",
        "fecha_remito": "2026-07-17",
        "fecha_ticket": "2026-07-17",
        "remito_tipo": "002",
        "remito_sucursal": "003",
        "remito_numero": "0003755",
        "cliente_candidato": "Alcogreen S.A.",
        "proveedor_candidato": "Forestal Paraguay S.A.",
        "peso_bruto": "48.250,00",
        "tara": "16.460,00",
        "neto": "31.790,00",
        "unidad_peso": "kg",
        "patente_observada": "AAXO300",
        "chofer_observado": "YVAN PINTOS",
        "confidence": {},
        "warnings": [],
    }
    vision = type("Vision", (), {"analyze": lambda self, path: vision_data})()
    engine = create_engine("sqlite:///:memory:")
    models.Cliente.__table__.create(engine)
    models.Proveedor.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    db.add_all([
        models.Cliente(id=7, razon_social="ALCOGREEN SRL", activo=True),
        models.Proveedor(id=9, razon_social="FORESTAL PARAGUAY SA", activo=True),
    ])
    db.commit()

    result = TripImageService(db, storage, vision).analyze(
        b"\xff\xd8\xffdata", "remito.jpg", "image/jpeg"
    )

    self.assertEqual(result["proposal"]["cliente_id"], 7)
    self.assertEqual(result["proposal"]["cliente_candidato"], "Alcogreen S.A.")
    self.assertEqual(result["proposal"]["proveedor_id"], 9)
    self.assertEqual(result["proposal"]["proveedor_candidato"], "Forestal Paraguay S.A.")
    self.assertEqual(result["proposal"]["numero_remision_fpv"], "002-003-0003755")
```

Agregar casos independientes:

```python
def test_analysis_keeps_each_unresolved_catalog_independent(self):
    import models

    service, db, vision_data = self.make_analysis_service()
    db.add_all([
        models.Cliente(id=7, razon_social="Alcogreen SA", activo=True),
        models.Cliente(id=8, razon_social="ALCOGREEN SRL", activo=True),
        models.Proveedor(id=9, razon_social="Forestal Paraguay SA", activo=True),
    ])
    db.commit()

    ambiguous_client = service.analyze(b"\xff\xd8\xffone", "a.jpg", "image/jpeg")
    proposal = ambiguous_client["proposal"]
    self.assertIsNone(proposal["cliente_id"])
    self.assertEqual(proposal["proveedor_id"], 9)
    self.assertTrue(any("Cliente sin coincidencia activa única" in warning for warning in proposal["warnings"]))

    db.query(models.Cliente).delete()
    db.query(models.Proveedor).delete()
    db.add(models.Cliente(id=7, razon_social="Alcogreen SA", activo=True))
    db.commit()
    missing_provider = service.analyze(b"\xff\xd8\xfftwo", "b.jpg", "image/jpeg")
    proposal = missing_provider["proposal"]
    self.assertEqual(proposal["cliente_id"], 7)
    self.assertIsNone(proposal["proveedor_id"])
    self.assertTrue(any("Proveedor sin coincidencia activa única" in warning for warning in proposal["warnings"]))
```

Agregar el helper a la clase:

```python
def make_analysis_service(self):
    from image_storage import ImageStorage
    from trip_image_service import TripImageService
    import models

    root = tempfile.TemporaryDirectory()
    self.addCleanup(root.cleanup)
    storage = ImageStorage(Path(root.name).resolve(), "x" * 32)
    vision_data = {
        "fecha_remision": "2026-07-17",
        "fecha_remito": "2026-07-17",
        "fecha_ticket": "2026-07-17",
        "remito_tipo": "002",
        "remito_sucursal": "003",
        "remito_numero": "0003755",
        "cliente_candidato": "Alcogreen S.A.",
        "proveedor_candidato": "Forestal Paraguay S.A.",
        "peso_bruto": "48.250,00",
        "tara": "16.460,00",
        "neto": "31.790,00",
        "unidad_peso": "kg",
        "patente_observada": "AAXO300",
        "chofer_observado": "YVAN PINTOS",
        "confidence": {},
        "warnings": [],
    }
    vision = type(
        "Vision",
        (),
        {"analyze": lambda self, path: vision_data},
    )()
    engine = create_engine("sqlite:///:memory:")
    models.Cliente.__table__.create(engine)
    models.Proveedor.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    service = TripImageService(db, storage, vision)
    return service, db, vision_data
```

- [ ] **Step 2: Ejecutar el test y verificar que falle**

Run:

```powershell
py -m pytest backend/test_trip_image_api.py -q
```

Expected: `FAIL`; la propuesta no contiene cliente y el servicio consulta solamente proveedores.

- [ ] **Step 3: Ampliar el esquema de propuesta**

En `backend/schemas.py`, definir:

```python
class TripImageProposal(BaseModel):
    fecha_remision: date
    numero_remision_fpv: str = Field(pattern=r"^[0-9]{3}-[0-9]{3}-[0-9]{7}$")
    cliente_id: Optional[int] = None
    cliente_candidato: Optional[str] = None
    proveedor_id: Optional[int] = None
    proveedor_candidato: Optional[str] = None
    peso_bruto_destino: Decimal
    tara_destino: Decimal
    neto_destino: Decimal
    patente_observada: Optional[str] = None
    chofer_observado: Optional[str] = None
    confidence: dict[str, float]
    warnings: List[str]

    @field_validator("peso_bruto_destino", "tara_destino", "neto_destino")
    @classmethod
    def finite_proposal_weights(cls, value):
        if not value.is_finite():
            raise ValueError("El peso debe ser finito")
        return value

    @field_validator("confidence")
    @classmethod
    def valid_confidence(cls, value):
        if any(not math.isfinite(score) or score < 0 or score > 1 for score in value.values()):
            raise ValueError("La confianza debe estar entre 0 y 1")
        return value
```

- [ ] **Step 4: Implementar la resolución genérica en el servicio**

En `backend/trip_image_service.py`, importar `normalize_business_name` y agregar:

```python
def _resolve_unique_active(db, model, normalized_name):
    candidates = db.query(model.id, model.razon_social).filter(
        model.activo.is_(True)
    ).all()
    matches = [
        row for row in candidates
        if normalize_business_name(row.razon_social) == normalized_name
    ]
    return matches[0].id if len(matches) == 1 else None
```

En `TripImageService.analyze`, reemplazar la consulta exclusiva de proveedor:

```python
normalized = normalize_extraction(raw)
client_id = _resolve_unique_active(
    self.db, models.Cliente, normalized.cliente_normalizado
)
provider_id = _resolve_unique_active(
    self.db, models.Proveedor, normalized.proveedor_normalizado
)
warnings = list(raw.get("warnings", []))
if client_id is None:
    warnings.append(
        "Cliente sin coincidencia activa única; seleccione un cliente para confirmar"
    )
if provider_id is None:
    warnings.append(
        "Proveedor sin coincidencia activa única; seleccione un proveedor para confirmar"
    )
return {
    "upload_token": temporary.token,
    "proposal": {
        "fecha_remision": normalized.fecha_remision,
        "numero_remision_fpv": normalized.numero_remision_fpv,
        "cliente_id": client_id,
        "cliente_candidato": raw.get("cliente_candidato"),
        "proveedor_id": provider_id,
        "proveedor_candidato": raw.get("proveedor_candidato"),
        "peso_bruto_destino": normalized.peso_bruto_destino,
        "tara_destino": normalized.tara_destino,
        "neto_destino": normalized.neto_destino,
        "patente_observada": raw.get("patente_observada"),
        "chofer_observado": raw.get("chofer_observado"),
        "confidence": raw.get("confidence", {}),
        "warnings": warnings,
    },
}
```

- [ ] **Step 5: Ejecutar las pruebas focales**

Run:

```powershell
py -m pytest backend/test_minimax_vision.py backend/test_trip_image_normalization.py backend/test_trip_image_api.py -q
```

Expected: `PASS`.

- [ ] **Step 6: Commit de análisis y resolución**

```powershell
git add backend/schemas.py backend/trip_image_service.py backend/test_trip_image_api.py
git commit -m "fix: resolver cliente y proveedor en precarga OCR"
```

### Task 4: Exigir y persistir ambos IDs al confirmar

**Files:**
- Modify: `backend/schemas.py:192-212`
- Modify: `backend/trip_image_service.py:79-100`
- Modify: `backend/trip_service.py:67-92`
- Modify: `backend/test_trip_image_api.py:372-395`
- Modify: `backend/test_trip_image_api.py:438-460`
- Modify: `backend/test_trip_image_api.py:560-680`

- [ ] **Step 1: Actualizar el fixture de confirmación**

En `make_confirm_fixture`, crear también la tabla y entidad cliente:

```python
for table in (
    models.Empleado.__table__,
    models.Cliente.__table__,
    models.Proveedor.__table__,
    models.Equipo.__table__,
    models.UnidadNegocio.__table__,
    models.TableroProduccion.__table__,
    models.ViajeImagen.__table__,
):
    table.create(engine)

db.add_all([
    user,
    models.Cliente(id=21, razon_social="Alcogreen", activo=True),
    models.Proveedor(id=20, razon_social="Forestal Paraguay", activo=True),
    models.UnidadNegocio(id=3, descripcion="Transporte", activo=True),
    models.Equipo(
        id=30,
        descripcion="Camion",
        patente="ABC123",
        nro_chasis="c",
        nro_motor="m",
        tipo_movil_id=1,
        activo=True,
        movil_asociado=0,
        ult_hr_km=0,
    ),
])
db.commit()

request = schemas.TripImageConfirmRequest(
    upload_token=saved.token,
    fecha_remision=date(2026, 7, 17),
    fecha_recepcion=date(2026, 7, 17),
    numero_remision_fpv="002-003-0003755",
    cliente_id=21,
    proveedor_id=20,
    patente="ABC123",
    unidad_negocio_id=3,
    peso_bruto_destino=48.250,
    tara_destino=16.460,
    neto_destino=31.790,
    observaciones="revisado",
)
```

- [ ] **Step 2: Escribir pruebas de obligatoriedad y persistencia**

Agregar:

```python
def test_confirm_schema_requires_client_and_provider(self):
    from schemas import TripImageConfirmRequest

    valid = {
        "upload_token": "x",
        "fecha_remision": date(2026, 7, 17),
        "fecha_recepcion": date(2026, 7, 17),
        "numero_remision_fpv": "002-003-0003755",
        "cliente_id": 21,
        "proveedor_id": 20,
        "patente": "ABC123",
        "unidad_negocio_id": 3,
        "peso_bruto_destino": 48.250,
        "tara_destino": 16.460,
        "neto_destino": 31.790,
    }
    for missing in ("cliente_id", "proveedor_id"):
        payload = dict(valid)
        payload.pop(missing)
        with self.subTest(missing=missing), self.assertRaises(ValueError):
            TripImageConfirmRequest(**payload)
```

Actualizar la prueba idempotente:

```python
def test_confirm_uses_current_user_persists_both_catalogs_and_is_idempotent(self):
    from trip_image_service import TripImageService

    db, storage, user, request, factory = self.make_confirm_fixture()
    service = TripImageService(db, storage, object(), session_factory=factory)
    first = service.confirm(request, user)
    second = service.confirm(request, user)
    self.assertEqual(first, second)

    trip = db.get(models.TableroProduccion, first["viaje_id"])
    self.assertEqual(trip.empleado_id, user.id)
    self.assertEqual(trip.cliente_id, 21)
    self.assertEqual(trip.proveedor_id, 20)
    self.assertTrue(trip.pesaje_unico)
    self.assertEqual(trip.neto_origen, Decimal("0.00"))
```

Agregar rechazos autoritativos:

```python
def test_confirm_rejects_missing_or_inactive_client_and_provider_without_writes(self):
    from trip_image_service import TripImageService

    for catalog, replacement_id in (("cliente", 999), ("proveedor", 999)):
        db, storage, user, request, factory = self.make_confirm_fixture()
        setattr(request, f"{catalog}_id", replacement_id)
        service = TripImageService(db, storage, object(), session_factory=factory)
        with self.subTest(catalog=catalog), self.assertRaises(HTTPException) as error:
            service.confirm(request, user)
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(db.query(models.TableroProduccion).count(), 0)
        self.assertEqual(db.query(models.ViajeImagen).count(), 0)
```

Agregar el caso de entidades inactivas:

```python
def test_confirm_rejects_inactive_client_and_provider_without_writes(self):
    from trip_image_service import TripImageService

    for catalog, model, entity_id in (
        ("cliente", models.Cliente, 21),
        ("proveedor", models.Proveedor, 20),
    ):
        db, storage, user, request, factory = self.make_confirm_fixture()
        entity = db.get(model, entity_id)
        entity.activo = False
        db.commit()
        service = TripImageService(db, storage, object(), session_factory=factory)

        with self.subTest(catalog=catalog), self.assertRaises(HTTPException) as error:
            service.confirm(request, user)

        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(db.query(models.TableroProduccion).count(), 0)
        self.assertEqual(db.query(models.ViajeImagen).count(), 0)
```

- [ ] **Step 3: Ejecutar los tests y verificar que fallen**

Run:

```powershell
py -m pytest backend/test_trip_image_api.py -q
```

Expected: `FAIL`; el request no exige cliente, la confirmación lo reemplaza por `None` y `trip_service` lo prohíbe en pesaje único.

- [ ] **Step 4: Exigir cliente en el request y trasladarlo al registro**

En `backend/schemas.py`, agregar el campo obligatorio:

```python
class TripImageConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_token: str
    fecha_remision: date
    fecha_recepcion: date
    numero_remision_fpv: str = Field(pattern=r"^[0-9]{3}-[0-9]{3}-[0-9]{7}$")
    cliente_id: int
    proveedor_id: int
    patente: str
    unidad_negocio_id: int
    peso_bruto_destino: float
    tara_destino: float
    neto_destino: float
    observaciones: Optional[str] = None
```

En `TripImageService.confirm`, cambiar la construcción:

```python
registro = schemas.RegistroViajeCreate(
    fecha_remision=request.fecha_remision,
    fecha_recepcion=request.fecha_recepcion,
    cliente_id=request.cliente_id,
    proveedor_id=request.proveedor_id,
    numero_remision="",
    numero_remision_fpv=request.numero_remision_fpv,
    chofer_id=current_user.id,
    patente=request.patente,
    unidad_negocio_id=request.unidad_negocio_id,
    pesaje_unico=True,
    peso_bruto_origen=0,
    tara_origen=0,
    neto_origen=0,
    peso_bruto_destino=request.peso_bruto_destino,
    tara_destino=request.tara_destino,
    neto_destino=request.neto_destino,
    observaciones=request.observaciones,
)
```

- [ ] **Step 5: Reemplazar la prohibición de cliente en pesaje único**

En `backend/trip_service.py`, agregar un helper:

```python
def _active_catalog_id(db, model, value, label):
    if value is None:
        raise HTTPException(status_code=400, detail=f"{label} requerido")
    entity = db.query(model).filter(model.id == value).first()
    if not entity or not entity.activo:
        raise HTTPException(status_code=400, detail=f"{label} no encontrado")
    return entity.id
```

Reemplazar `_catalogs` por:

```python
def _catalogs(db, registro):
    unidad = db.query(models.UnidadNegocio).filter(
        models.UnidadNegocio.id == registro.unidad_negocio_id
    ).first()
    if not unidad or not unidad.activo:
        raise HTTPException(status_code=400, detail="Unidad de negocio no encontrada")

    proveedor_id = None
    if registro.proveedor_id is not None:
        proveedor_id = _active_catalog_id(
            db, models.Proveedor, registro.proveedor_id, "Proveedor"
        )

    if registro.pesaje_unico:
        if proveedor_id is None:
            raise HTTPException(status_code=400, detail="Proveedor requerido")
        cliente_id = _active_catalog_id(
            db, models.Cliente, registro.cliente_id, "Cliente"
        )
    else:
        cliente_id = _active_catalog_id(
            db,
            models.Cliente,
            registro.cliente_id if registro.cliente_id is not None else 1,
            "Cliente",
        )
    return proveedor_id, cliente_id
```

Esto conserva la regla manual existente: fuera de pesaje único, cliente omitido continúa usando el ID predeterminado `1`.

- [ ] **Step 6: Ejecutar pruebas backend focales**

Run:

```powershell
py -m pytest backend/test_trip_image_api.py backend/test_trip_image_normalization.py backend/test_minimax_vision.py -q
```

Expected: `PASS`.

- [ ] **Step 7: Ejecutar regresión completa del backend**

Run:

```powershell
py -m pytest backend -q
py -m py_compile backend/main.py backend/schemas.py backend/trip_image_service.py backend/trip_service.py
```

Expected: ambas órdenes terminan con exit code `0`.

- [ ] **Step 8: Commit de confirmación**

```powershell
git add backend/schemas.py backend/trip_image_service.py backend/trip_service.py backend/test_trip_image_api.py
git commit -m "fix: exigir cliente y proveedor en viajes OCR"
```

### Task 5: Incorporar ambos catálogos al modelo de revisión

**Files:**
- Modify: `frontend/src/services/tripImageReview.js:45-73`
- Modify: `frontend/src/services/tripImageReview.js:126-142`
- Modify: `frontend/src/services/tripImageReview.js:160-201`
- Modify: `frontend/tests/tripImage.test.js:95-150`
- Modify: `frontend/tests/tripImage.test.js:230-290`

- [ ] **Step 1: Ampliar fixtures y expectativas frontend**

En `frontend/tests/tripImage.test.js`, definir ambos catálogos:

```javascript
const catalog = {
  empleados: [{ id: 7, nombre: ' Ana ', apellido: ' Pérez ', activo: true }],
  equipos: [{ id: 2, patente: 'AB 123 CD', descripcion: ' Camión ', activo: true }],
  unidadesNegocio: [{ id: 4, descripcion: ' Forestal ', prefijo: ' F ', activo: true }],
  clientes: [
    { id: 10, razon_social: 'Alcogreen', activo: true },
    { id: 11, razon_social: 'Cliente inactivo', activo: false },
  ],
  proveedores: [
    { id: 8, razon_social: 'Forestal Paraguay', activo: true },
    { id: 9, razon_social: 'Proveedor inactivo', activo: false },
  ],
}
```

El análisis de referencia será:

```javascript
const analysis = {
  upload_token: 'opaque',
  proposal: {
    fecha_remision: '2026-07-17',
    numero_remision_fpv: '002-003-0003755',
    cliente_id: 10,
    cliente_candidato: 'Alcogreen S.A.',
    proveedor_id: 8,
    proveedor_candidato: 'Forestal Paraguay S.A.',
    peso_bruto_destino: 48.250,
    tara_destino: 16.460,
    neto_destino: 31.790,
    warnings: [],
  },
}
```

Actualizar la expectativa de configuración:

```javascript
assert.deepEqual(result.activeClientIds, [10])
assert.deepEqual(result.activeProviderIds, [8])
assert.ok(Object.isFrozen(result.activeClientIds))
assert.ok(Object.isFrozen(result.activeProviderIds))
```

Actualizar la expectativa del modelo:

```javascript
assert.equal(review.cliente_id, 10)
assert.equal(review.cliente_candidato, 'Alcogreen S.A.')
assert.equal(review.proveedor_id, 8)
assert.equal(review.proveedor_candidato, 'Forestal Paraguay S.A.')
```

- [ ] **Step 2: Exigir ambos IDs en las pruebas de payload**

La expectativa de claves será:

```javascript
assert.deepEqual(Object.keys(payload), [
  'upload_token',
  'fecha_remision',
  'fecha_recepcion',
  'numero_remision_fpv',
  'cliente_id',
  'proveedor_id',
  'patente',
  'unidad_negocio_id',
  'peso_bruto_destino',
  'tara_destino',
  'neto_destino',
  'observaciones',
])
assert.equal(payload.cliente_id, 10)
assert.equal(payload.proveedor_id, 8)
```

Agregar casos de rechazo:

```javascript
for (const mutate of [
  (review) => { review.cliente_id = null },
  (review) => { review.proveedor_id = null },
  (review) => { review.cliente_id = 11 },
  (review) => { review.proveedor_id = 9 },
]) {
  const invalid = structuredClone(valid)
  mutate(invalid)
  assert.throws(
    () => buildConfirmPayload(invalid, settings),
    /cliente|proveedor/i,
  )
}
```

- [ ] **Step 3: Ejecutar los tests y verificar que fallen**

Run:

```powershell
Set-Location frontend
node --test tests/tripImage.test.js
Set-Location ..
```

Expected: `FAIL`; no existen `activeClientIds`, `cliente_id` ni `cliente_candidato`.

- [ ] **Step 4: Incorporar clientes activos al snapshot**

En `readTripImageSettings`, construir:

```javascript
const activeClientIds = Object.freeze(list(catalog.clientes)
  .filter((item) => item?.activo === true)
  .map((item) => positiveInteger(item.id))
  .filter(Boolean))
const activeProviderIds = Object.freeze(list(catalog.proveedores)
  .filter((item) => item?.activo === true)
  .map((item) => positiveInteger(item.id))
  .filter(Boolean))
```

Incluir ambos en el objeto congelado retornado:

```javascript
return Object.freeze({
  userId,
  user,
  patente,
  equipoId,
  equipo,
  unidadNegocioId,
  unidadNegocio,
  activeClientIds,
  activeProviderIds,
  missing: Object.freeze(missing),
  errors: Object.freeze(errors),
  complete: missing.length === 0,
})
```

- [ ] **Step 5: Ampliar el modelo y el payload**

En `createReviewModel`, agregar:

```javascript
cliente_id: proposal.cliente_id ?? null,
cliente_candidato: proposal.cliente_candidato ?? null,
proveedor_id: proposal.proveedor_id ?? null,
proveedor_candidato: proposal.proveedor_candidato ?? null,
```

En `buildConfirmPayload`, validar ambos IDs:

```javascript
const clienteId = positiveInteger(review?.cliente_id)
if (
  !clienteId
  || !Array.isArray(settings?.activeClientIds)
  || !settings.activeClientIds.includes(clienteId)
) {
  throw new TypeError('Seleccioná un cliente activo válido.')
}
const proveedorId = positiveInteger(review?.proveedor_id)
if (
  !proveedorId
  || !Array.isArray(settings?.activeProviderIds)
  || !settings.activeProviderIds.includes(proveedorId)
) {
  throw new TypeError('Seleccioná un proveedor activo válido.')
}
```

Incluir en el objeto retornado:

```javascript
cliente_id: clienteId,
proveedor_id: proveedorId,
```

- [ ] **Step 6: Ejecutar las pruebas unitarias frontend**

Run:

```powershell
Set-Location frontend
node --test tests/tripImage.test.js
Set-Location ..
```

Expected: `PASS`.

- [ ] **Step 7: Commit del modelo frontend**

```powershell
git add frontend/src/services/tripImageReview.js frontend/tests/tripImage.test.js
git commit -m "fix: validar cliente y proveedor en revision OCR"
```

### Task 6: Mostrar dos selectores obligatorios

**Files:**
- Modify: `frontend/src/views/TripImageUpload.vue:33-40`
- Modify: `frontend/src/views/TripImageUpload.vue:245-258`
- Modify: `frontend/tests/tripImageUpload.spec.js:10-48`
- Modify: `frontend/tests/tripImageUpload.spec.js:70-165`

- [ ] **Step 1: Actualizar el fixture de la vista**

En `frontend/tests/tripImageUpload.spec.js`, usar:

```javascript
catalog: {
  empleados: [{ id: 7, nombre: 'Ana', apellido: 'Pérez', activo: true }],
  clientes: [
    { id: 10, razon_social: 'Alcogreen', activo: true },
    { id: 11, razon_social: 'Cliente inactivo', activo: false },
  ],
  proveedores: [
    { id: 8, razon_social: 'Forestal Paraguay', activo: true },
    { id: 9, razon_social: 'Proveedor inactivo', activo: false },
  ],
  equipos: [{ id: 2, patente: 'AB 123 CD', descripcion: 'Camión', activo: true }],
  unidadesNegocio: [{ id: 4, descripcion: 'Forestal', prefijo: 'F', activo: true }],
  isOffline: false,
  fetchCatalogues: vi.fn(async () => ({})),
},
```

Y:

```javascript
const analysis = {
  upload_token: 'opaque',
  proposal: {
    fecha_remision: '2026-07-17',
    numero_remision_fpv: '002-003-0003755',
    cliente_id: 10,
    cliente_candidato: 'Alcogreen S.A.',
    proveedor_id: 8,
    proveedor_candidato: 'Forestal Paraguay S.A.',
    peso_bruto_destino: 48.250,
    tara_destino: 16.460,
    neto_destino: 31.790,
    warnings: [],
  },
}
```

- [ ] **Step 2: Agregar pruebas de render y bloqueo**

Agregar:

```javascript
it('renders active client and provider selectors with OCR proposals selected', async () => {
  const wrapper = await mountView()
  await selectFile(wrapper, file())

  const client = wrapper.get('select[aria-label="Cliente"]')
  const provider = wrapper.get('select[aria-label="Proveedor"]')
  expect(client.element.value).toBe('10')
  expect(provider.element.value).toBe('8')
  expect(client.text()).toContain('Alcogreen')
  expect(client.text()).not.toContain('Cliente inactivo')
  expect(provider.text()).toContain('Forestal Paraguay')
  expect(provider.text()).not.toContain('Proveedor inactivo')
})

it.each([
  ['cliente', { cliente_id: null }, 'Seleccioná un cliente activo válido.'],
  ['proveedor', { proveedor_id: null }, 'Seleccioná un proveedor activo válido.'],
])('does not confirm without %s', async (_label, proposalChange, message) => {
  mocks.analyze.mockResolvedValueOnce({
    ...analysis,
    proposal: { ...analysis.proposal, ...proposalChange },
  })
  const wrapper = await mountView()
  await selectFile(wrapper, file())
  await wrapper.get('form').trigger('submit')
  await flushPromises()

  expect(mocks.confirm).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain(message)
})
```

Actualizar la prueba de error/reintento para seleccionar o conservar también cliente y proveedor, y comprobar:

```javascript
expect(wrapper.get('select[aria-label="Cliente"]').element.value).toBe('10')
expect(wrapper.get('select[aria-label="Proveedor"]').element.value).toBe('8')
```

- [ ] **Step 3: Ejecutar el test y verificar que falle**

Run:

```powershell
Set-Location frontend
npx vitest run tests/tripImageUpload.spec.js
Set-Location ..
```

Expected: `FAIL`; la vista no tiene selector de cliente.

- [ ] **Step 4: Agregar catálogos activos y selectores**

En `<script setup>`:

```javascript
const activeClients = computed(() =>
  catalog.clientes.filter((item) => item.activo === true)
)
const activeProviders = computed(() =>
  catalog.proveedores.filter((item) => item.activo === true)
)
```

En la sección de revisión, antes de los pesos:

```vue
<label class="block text-xs font-medium text-gray-600 dark:text-gray-300">
  Cliente
  <select
    v-model.number="review.cliente_id"
    required
    aria-label="Cliente"
    class="mt-1 min-h-11 w-full rounded-lg border p-2 dark:border-gray-600 dark:bg-gray-700"
  >
    <option :value="null">Seleccionar cliente</option>
    <option
      v-for="client in activeClients"
      :key="client.id"
      :value="client.id"
    >
      {{ client.razon_social || client.nombre || client.descripcion }}
    </option>
  </select>
</label>
<label class="block text-xs font-medium text-gray-600 dark:text-gray-300">
  Proveedor
  <select
    v-model.number="review.proveedor_id"
    required
    aria-label="Proveedor"
    class="mt-1 min-h-11 w-full rounded-lg border p-2 dark:border-gray-600 dark:bg-gray-700"
  >
    <option :value="null">Seleccionar proveedor</option>
    <option
      v-for="provider in activeProviders"
      :key="provider.id"
      :value="provider.id"
    >
      {{ provider.razon_social || provider.nombre || provider.descripcion }}
    </option>
  </select>
</label>
```

No deshabilitar el botón exclusivamente por los selectores: `buildConfirmPayload` debe conservar el mensaje específico y el backend seguirá siendo la autoridad.

- [ ] **Step 5: Ejecutar pruebas de componente y frontend completo**

Run:

```powershell
Set-Location frontend
npx vitest run tests/tripImageUpload.spec.js
npm run verify
Set-Location ..
```

Expected: ambas órdenes terminan con exit code `0`.

- [ ] **Step 6: Commit de pantalla**

```powershell
git add frontend/src/views/TripImageUpload.vue frontend/tests/tripImageUpload.spec.js
git commit -m "fix: pedir cliente y proveedor en precarga OCR"
```

### Task 7: Actualizar documentación y verificar el caso de referencia

**Files:**
- Modify: `README.md:109-114`
- Modify: `README.md:281-298`

- [ ] **Step 1: Corregir la descripción operativa**

Reemplazar el párrafo que afirma `cliente_id=NULL` por:

```markdown
El flujo **Cargar desde foto** envía JPEG, PNG o WebP al backend, extrae una propuesta con MiniMax y recién crea el viaje cuando el operador revisa y confirma. La imagen queda privada: se entrega únicamente por el endpoint autenticado, nunca como archivo estático. El OCR puede informar chofer y patente observados, pero el registro usa el usuario autenticado y la patente/unidad configuradas en el celular. El destinatario se propone como cliente y el remitente como proveedor; ambos deben seleccionarse desde sus catálogos activos antes de confirmar. El remito del proveedor queda vacío; el remito FGPY se conserva completo. Para este trayecto se guarda `pesaje_unico=true`, origen en cero y destino en toneladas.
```

- [ ] **Step 2: Documentar la verificación segura con la imagen**

Agregar al final de `Verificación del flujo OCR`:

```markdown
Para verificar el documento de referencia sin escribir en producción:

1. usar una base local o de staging con Alcogreen como cliente activo y Forestal Paraguay como proveedor activo;
2. cargar la imagen mediante `Cargar desde foto`;
3. detenerse en `Revisá los datos detectados`, sin pulsar `Confirmar y guardar`;
4. comprobar remito `002-003-0003755`, cliente Alcogreen, proveedor Forestal Paraguay y pesos `48.250 / 16.460 / 31.790 TN`;
5. comprobar que al vaciar cliente o proveedor la confirmación no se envía.

La lectura de referencia no debe consultar ni escribir una base de producción.
```

- [ ] **Step 3: Ejecutar la batería completa**

Run:

```powershell
py -m pytest backend -q
Set-Location frontend
npm run verify
Set-Location ..
```

Expected: ambas órdenes terminan con exit code `0`.

- [ ] **Step 4: Verificar el caso de referencia en entorno seguro**

Con backend y frontend locales o de staging:

1. abrir `Cargar desde foto`;
2. cargar `C:\Users\Ventas\AppData\Local\Temp\codex-clipboard-fc2929a5-029f-4f98-9803-8d1357c584b7.png`;
3. comprobar en la revisión, sin confirmar:
   - remito `002-003-0003755`;
   - cliente seleccionado `Alcogreen`;
   - proveedor seleccionado `Forestal Paraguay`;
   - bruto `48.250`;
   - tara `16.460`;
   - neto `31.790`;
4. limpiar cliente y pulsar confirmar: debe aparecer `Seleccioná un cliente activo válido.` y no debe existir una llamada de confirmación;
5. restaurar cliente, limpiar proveedor y pulsar confirmar: debe aparecer `Seleccioná un proveedor activo válido.` y no debe existir una llamada de confirmación.

Expected: todos los valores coinciden y no se crea ningún viaje durante esta verificación.

- [ ] **Step 5: Revisar el diff final**

Run:

```powershell
git diff --check
git status -sb
git diff --stat HEAD~6..HEAD
```

Expected: `git diff --check` no informa errores; el estado solamente contiene cambios deliberados y archivos preexistentes no relacionados.

- [ ] **Step 6: Commit de documentación**

```powershell
git add README.md
git commit -m "docs: actualizar validacion comercial del OCR"
```

## Criterio de finalización

La implementación no se considera completa hasta que exista evidencia fresca de:

- pruebas completas backend en verde;
- `npm run verify` en verde;
- propuesta OCR con cliente y proveedor separados;
- rechazo frontend de cada selección faltante;
- rechazo backend de cada ID inexistente o inactivo;
- persistencia de ambos IDs en la prueba transaccional;
- revisión segura de la imagen de referencia sin crear un viaje real;
- ausencia de cambios accidentales en el flujo manual, almacenamiento de imágenes, configuración de chofer/patente/unidad y cálculo de pesos.
