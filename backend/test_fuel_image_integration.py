"""End-to-end integration tests for fuel image flow using real-world data.

Cubre dos casos de humo basados en las fotos reales compartidas por
Oscar en julio 2026:

- Ticket Petrobras: BOLETA 005577061024, RUC 80015646-0, fecha 30/07/2026
  13:30:56, km del vehiculo 3362, litros 430, producto DIESEL EURO 5 S-50.
  Tarjeta 7002650831010234.
- Ticket Lider Express: BOLETA 005572608217, RUC 80073986-8, fecha
  28/07/2026 22:37:57, km 77422, litros 300, producto DIESEL EURO 5 S-50.
  Tarjeta 70026508310100307.
- Remito interno Forestal Paraguay #0007222: fecha 30/07/26, hora
  13:42, litros 162, km 7153.1, lugar Gsibg, firmante Fernando, tipo
  INTERNO/GASOIL.

Los tests no tocan MiniMax; usan un FakeVision que devuelve la
extraccion esperada (lo que MiniMax deberia devolver para esas fotos).
El objetivo es asegurar que el normalizador + service + endpoints
producen los datos correctos cuando el OCR acierta.

Para un smoke real con MiniMax, ver scripts/smoke_fuel_image.sh.
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
import schemas
from fuel_image_service import FuelImageService
from image_storage import ImageStorage
from minimax_vision import (
    FUEL_TICKET_SCHEMA,
    FUEL_REMITO_SCHEMA,
    MiniMaxVisionError,
)


SECRET = "fuel-integration-test-secret-that-is-at-least-thirty-two-bytes"
JPEG = b"\xff\xd8\xff" + b"fuel-integration"
NOW = datetime(2026, 7, 31, 12, tzinfo=timezone.utc)


# --- Datos reales extraídos manualmente de las fotos compartidas ---

PETROBRAS_TICKET_OCR = {
    "fecha": "30/07/2026",
    "hora": "13:30:56",
    "litros": "430",
    "km_hora": "3362",
    "remito": "9938226",
    "ruc_emisor": "80015646-0",
    "razon_social_emisor": "PETROBRAS",
    "producto": "DIESEL EURO 5 S-50",
    "nro_tarjeta": "7002650831010234",
    "confidence": {
        "fecha": 0.95, "hora": 0.95, "litros": 0.95, "km_hora": 0.9,
        "remito": 0.9, "ruc_emisor": 0.85, "razon_social_emisor": 0.95,
        "producto": 0.95, "nro_tarjeta": 0.8,
    },
    "warnings": [],
}


LIDER_TICKET_OCR = {
    "fecha": "28/07/2026",
    "hora": "22:37:57",
    "litros": "300",
    "km_hora": "77422",
    "remito": "9925673",
    "ruc_emisor": "80073986-8",
    "razon_social_emisor": "LIDER EXPRESS",
    "producto": "DIESEL EURO 5 S-50",
    "nro_tarjeta": "70026508310100307",
    "confidence": {
        "fecha": 0.95, "hora": 0.95, "litros": 0.9, "km_hora": 0.95,
        "remito": 0.9, "ruc_emisor": 0.85, "razon_social_emisor": 0.95,
        "producto": 0.95, "nro_tarjeta": 0.7,
    },
    "warnings": [],
}


REMITO_0007222_OCR = {
    "fecha": "30/07/26",
    "hora": "13:42",
    "litros": "162",
    "kilometros": "7153.1",
    "remito": "0007222",
    "lugar_carga": "Gsibg",
    "patente_observada": "AAXO300",
    "firmante": "Fernando",
    "contacto": "nambiarifernando@forestalparaguay.com.ar",
    "tipo": "INTERNO/GASOIL",
    "confidence": {
        "fecha": 0.95, "hora": 0.9, "litros": 0.85, "kilometros": 0.6,
        "remito": 0.95, "lugar_carga": 0.4, "patente_observada": 0.5,
        "firmante": 0.7, "contacto": 0.95, "tipo": 0.95,
    },
    "warnings": ["letra ilegible en lugar_carga"],
}


class FakeVision:
    """Vision mockeado que devuelve la respuesta esperada sin llamar a MiniMax."""

    def __init__(self, response: dict):
        self.response = response
        self.last_schema = None

    def analyze(self, image_path, prompt=None, schema=None):
        self.last_schema = schema
        return self.response


class FuelIntegrationTestBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.storage = ImageStorage(
            root=self.root, token_secret=SECRET, now=lambda: NOW
        )
        self.engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.empleado = models.Empleado(
            id=1, nombre="Chofer", apellido="Test", email="c@t", telefono="",
            fecha_contratacion=datetime(2024, 1, 1).date(),
            activo=True, porcentaje=0.0,
        )
        self.db.add(self.empleado)
        if not self.db.get(models.UnidadNegocio, 1):
            self.db.add(models.UnidadNegocio(id=1, descripcion="Forestal", activo=True))
        self.equipo = models.Equipo(
            id=1, descripcion="Scania", patente="AAXO300",
            nro_chasis="CHS1", nro_motor="MTR1",
            tipo_movil_id=4, movil_asociado=0,
            activo=True, ult_hr_km=0,
        )
        self.db.add(self.equipo)
        self.paniol = models.Paniol(
            id=1, descripcion="Tanque 1", activo=True, unidad_negocio_id=1
        )
        self.db.add(self.paniol)
        self.interno = models.Proveedor(
            razon_social="INTERNO FORESTAL PARAGUAY", activo=True
        )
        self.db.add(self.interno)
        self.db.commit()

    def _service(self, vision: FakeVision) -> FuelImageService:
        return FuelImageService(
            self.db, self.storage, vision=vision, session_factory=self.Session
        )


class PetrobrasTicketIntegrationTest(FuelIntegrationTestBase):
    """Test del flujo completo con los datos del ticket Petrobras real."""

    def test_analyze_returns_expected_proposal(self):
        vision = FakeVision(response=PETROBRAS_TICKET_OCR)
        out = self._service(vision).analyze(
            JPEG, "ticket.jpg", "image/jpeg", schemas.FuelTipoComprobante.ticket
        )
        # Vision se llamo con el schema de ticket
        self.assertIs(vision.last_schema, FUEL_TICKET_SCHEMA)
        proposal = out["proposal"]
        # Campos basicos
        self.assertEqual(proposal["fecha"], "2026-07-30")
        self.assertEqual(proposal["hora"], "13:30:56")
        self.assertEqual(proposal["litros"], "430")
        self.assertEqual(proposal["km_hora"], 3362)
        self.assertEqual(proposal["remito"], "9938226")
        self.assertEqual(proposal["ruc"], "80015646-0")
        self.assertEqual(proposal["razon_social_emisor"], "PETROBRAS")
        self.assertEqual(proposal["producto"], "DIESEL EURO 5 S-50")
        # Proveedor: RUC 80015646 no existe, se crea inactivo
        self.assertIsNotNone(proposal["proveedor_id"])
        proveedor = self.db.get(models.Proveedor, proposal["proveedor_id"])
        self.assertFalse(proveedor.activo)
        self.assertEqual(proveedor.cuit, "800156460")  # normalizado a digitos
        # Warning explicito sobre el proveedor nuevo
        self.assertTrue(any("Proveedor nuevo" in w for w in proposal["warnings"]))

    def test_confirm_happy_path_creates_movimiento_with_real_data(self):
        vision = FakeVision(response=PETROBRAS_TICKET_OCR)
        service = self._service(vision)
        out = service.analyze(
            JPEG, "ticket.jpg", "image/jpeg", schemas.FuelTipoComprobante.ticket
        )
        # Confirmar con los datos del proposal
        request = schemas.FuelTicketConfirmRequest(
            upload_token=out["upload_token"],
            fecha_carga=date.fromisoformat(out["proposal"]["fecha"]),
            litros=Decimal(out["proposal"]["litros"]),
            km_hora=out["proposal"]["km_hora"],
            equipo_id=self.equipo.id,
            paniol_id=self.paniol.id,
            proveedor_id=out["proposal"]["proveedor_id"],
            remito=out["proposal"]["remito"],
            observaciones="Smoke Petrobras 30/07/2026",
        )
        result = service.confirm_ticket(request, self.empleado)
        self.assertIn("movimiento_id", result)
        self.assertIn("imagen_id", result)
        mov = self.db.get(models.MovimientoCombustible, result["movimiento_id"])
        self.assertEqual(mov.fecha, date(2026, 7, 30))
        self.assertEqual(mov.km_hora, 3362.0)
        self.assertEqual(mov.remito, "9938226")
        # proveedor_id es el nuevo creado
        self.assertEqual(mov.proveedor_id, out["proposal"]["proveedor_id"])
        # paniol_id mapea unidad_negocio_id correctamente
        self.assertEqual(mov.unidad_negocio_id, 1)
        # periodo YYYYMM
        self.assertEqual(mov.periodo, "202607")
        # imagen creada y asociada
        img = self.db.get(models.CombustibleImagen, result["imagen_id"])
        self.assertEqual(img.movimiento_id, mov.id)
        # token_hash coincide con el hash del token
        expected_hash = hashlib.sha256(out["upload_token"].encode("utf-8")).hexdigest()
        self.assertEqual(img.token_hash, expected_hash)
        # El movimiento es del chofer autenticado
        self.assertEqual(mov.usuario, "1")


class LiderTicketIntegrationTest(FuelIntegrationTestBase):
    """Test con los datos del ticket Lider Express (segundo combustible)."""

    def test_analyze_resolves_diesel_product_and_creates_proveedor(self):
        vision = FakeVision(response=LIDER_TICKET_OCR)
        out = self._service(vision).analyze(
            JPEG, "lider.jpg", "image/jpeg", schemas.FuelTipoComprobante.ticket
        )
        proposal = out["proposal"]
        self.assertEqual(proposal["razon_social_emisor"], "LIDER EXPRESS")
        self.assertEqual(proposal["producto"], "DIESEL EURO 5 S-50")
        # DIESEL EURO 5 mapea a tipo_combustible_id=1 en el service
        self.assertEqual(proposal["tipo_combustible_id"], 1)
        # RUC 80073986 no existe, se crea proveedor
        self.assertIsNotNone(proposal["proveedor_id"])
        proveedor = self.db.get(models.Proveedor, proposal["proveedor_id"])
        self.assertEqual(proveedor.cuit, "800739868")
        self.assertEqual(proveedor.razon_social, "LIDER EXPRESS")


class RemitoInternoIntegrationTest(FuelIntegrationTestBase):
    """Test con los datos del remito interno #0007222 (Forestal Paraguay)."""

    def test_analyze_returns_remito_proposal_with_interno(self):
        vision = FakeVision(response=REMITO_0007222_OCR)
        out = self._service(vision).analyze(
            JPEG, "remito.jpg", "image/jpeg", schemas.FuelTipoComprobante.remito_interno
        )
        # Vision se llamo con el schema de remito
        self.assertIs(vision.last_schema, FUEL_REMITO_SCHEMA)
        proposal = out["proposal"]
        # Campos basicos
        self.assertEqual(proposal["fecha"], "2026-07-30")
        self.assertEqual(proposal["litros"], "162")
        self.assertEqual(proposal["kilometros"], "7153.1")
        self.assertEqual(proposal["remito"], "0007222")
        # INTERNO forzado por el service
        self.assertEqual(proposal["proveedor_id"], self.interno.id)
        self.assertEqual(proposal["proveedor_nombre"], "INTERNO FORESTAL PARAGUAY")
        # Datos manuscritos preservados
        self.assertEqual(proposal["lugar_carga"], "Gsibg")
        self.assertEqual(proposal["firmante"], "Fernando")
        self.assertEqual(proposal["contacto"], "nambiarifernando@forestalparaguay.com.ar")
        self.assertEqual(proposal["tipo"], "INTERNO/GASOIL")
        # Warning del OCR sobre letra ilegible se preserva
        self.assertIn("letra ilegible en lugar_carga", proposal["warnings"])

    def test_confirm_remito_uses_interno_regardless_of_payload(self):
        vision = FakeVision(response=REMITO_0007222_OCR)
        service = self._service(vision)
        out = service.analyze(
            JPEG, "remito.jpg", "image/jpeg", schemas.FuelTipoComprobante.remito_interno
        )
        # El payload del frontend NO lleva proveedor_id, pero el backend
        # lo fuerza al INTERNO. Simulamos eso.
        request = schemas.FuelRemitoInternoConfirmRequest(
            upload_token=out["upload_token"],
            fecha_carga=date.fromisoformat(out["proposal"]["fecha"]),
            litros=Decimal(out["proposal"]["litros"]),
            km_hora=Decimal(out["proposal"]["kilometros"]),
            equipo_id=self.equipo.id,
            paniol_id=self.paniol.id,
            remito=out["proposal"]["remito"],
            tipo_combustible_id=out["proposal"]["tipo_combustible_id"],
            observaciones="Smoke remito 0007222 - tipo INTERNO/GASOIL",
        )
        result = service.confirm_remito_interno(request, self.empleado)
        mov = self.db.get(models.MovimientoCombustible, result["movimiento_id"])
        # Verifica que se uso el INTERNO, no cualquier otro proveedor
        self.assertEqual(mov.proveedor_id, self.interno.id)
        self.assertEqual(mov.remito, "0007222")
        self.assertEqual(mov.km_hora, 7153.1)


class CrossTypeIntegrationTest(FuelIntegrationTestBase):
    """Tests cruzados: el mismo backend no debe mezclar tipos."""

    def test_ticket_schema_not_used_for_remito(self):
        vision = FakeVision(response=PETROBRAS_TICKET_OCR)
        self._service(vision).analyze(
            JPEG, "x.jpg", "image/jpeg", schemas.FuelTipoComprobante.remito_interno
        )
        # Si se pidio remito_interno, el schema llamado es el de remito,
        # no el de ticket (aunque el response mockeado no encaje).
        self.assertIs(vision.last_schema, FUEL_REMITO_SCHEMA)

    def test_remito_schema_not_used_for_ticket(self):
        """El service usa el schema segun `tipo`, no segun el contenido del OCR.

        Desde 2026-08-01 el normalizador de ticket es permisivo (acepta
        null en fecha/km_hora), asi que un payload tipo remito pasa la
        normalizacion con km_hora y campos-de-viaje en null. El test
        verifica que el schema elegido por el service es el de ticket."""
        vision = FakeVision(response=REMITO_0007222_OCR)
        service = self._service(vision)
        result = service.analyze(
            JPEG, "x.jpg", "image/jpeg", schemas.FuelTipoComprobante.ticket
        )
        # El service eligio el schema de ticket (no el de remito), aunque
        # el contenido del OCR sea de un remito.
        self.assertIs(vision.last_schema, FUEL_TICKET_SCHEMA)
        self.assertEqual(result["tipo"], "ticket")

    def test_vision_error_does_not_create_db_rows(self):
        """Si MiniMax falla, no se persisten movimientos ni imagenes.
        El temporal queda en storage para el cleanup diario (mismo
        comportamiento que trip_image_service)."""
        from minimax_vision import MiniMaxVisionError
        class BrokenVision:
            def analyze(self, *a, **k):
                raise MiniMaxVisionError("mock fail")
        with self.assertRaises(MiniMaxVisionError):
            self._service(BrokenVision()).analyze(
                JPEG, "x.jpg", "image/jpeg", schemas.FuelTipoComprobante.ticket
            )
        # Lo importante: no se creo nada en la DB
        self.assertEqual(self.db.query(models.MovimientoCombustible).count(), 0)
        self.assertEqual(self.db.query(models.CombustibleImagen).count(), 0)
        # El storage tiene 2 archivos (la imagen + su metadata .json):
        # el cleanup diario es responsable de purgarlo. No removemos
        # en analyze para mantener consistencia con el flujo de viaje.
        actual_files = [f for f in self.root.rglob("*") if f.is_file()]
        self.assertEqual(len(actual_files), 2)


class ConfirmErrorTest(FuelIntegrationTestBase):
    """Tests de errores en confirm: idempotencia, ownership, INTERNO ausente."""

    def test_confirm_idempotent_returns_same_result(self):
        vision = FakeVision(response=PETROBRAS_TICKET_OCR)
        service = self._service(vision)
        out = service.analyze(
            JPEG, "t.jpg", "image/jpeg", schemas.FuelTipoComprobante.ticket
        )
        request = schemas.FuelTicketConfirmRequest(
            upload_token=out["upload_token"],
            fecha_carga=date.fromisoformat(out["proposal"]["fecha"]),
            litros=Decimal("430"),
            km_hora=3362,
            equipo_id=1, paniol_id=1,
            proveedor_id=out["proposal"]["proveedor_id"],
            remito="9938226",
        )
        first = service.confirm_ticket(request, self.empleado)
        second = service.confirm_ticket(request, self.empleado)
        self.assertEqual(first, second)
        self.assertEqual(self.db.query(models.MovimientoCombustible).count(), 1)
        self.assertEqual(self.db.query(models.CombustibleImagen).count(), 1)

    def test_confirm_ticket_blocks_other_user_from_reusing_token(self):
        """El service bloquea con 403 si otro chofer quiere reusar un token ajeno."""
        from fastapi import HTTPException
        vision = FakeVision(response=PETROBRAS_TICKET_OCR)
        service = self._service(vision)
        out = service.analyze(
            JPEG, "t.jpg", "image/jpeg", schemas.FuelTipoComprobante.ticket
        )
        request = schemas.FuelTicketConfirmRequest(
            upload_token=out["upload_token"],
            fecha_carga=date.fromisoformat(out["proposal"]["fecha"]),
            litros=Decimal("430"),
            km_hora=3362,
            equipo_id=1, paniol_id=1,
            proveedor_id=out["proposal"]["proveedor_id"],
            remito="9938226",
        )
        service.confirm_ticket(request, self.empleado)
        # Otro chofer intenta reusar el mismo token: 403.
        otro_empleado = models.Empleado(
            id=99, nombre="Otro", apellido="Chofer", email="o@c", telefono="",
            fecha_contratacion=datetime(2024, 1, 1).date(),
            activo=True, porcentaje=0.0,
        )
        self.db.add(otro_empleado); self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            service.confirm_ticket(request, otro_empleado)
        self.assertEqual(ctx.exception.status_code, 403)
        # Sigue habiendo un solo movimiento
        self.assertEqual(self.db.query(models.MovimientoCombustible).count(), 1)

    def test_confirm_remito_fails_when_interno_missing_at_confirm(self):
        """Si el INTERNO desaparece entre el analyze y el confirm, el confirm
        falla con 503 (analiza y confirma con INTERNO presente, borramos,
        intentamos confirmar de nuevo)."""
        from fastapi import HTTPException
        vision = FakeVision(response=REMITO_0007222_OCR)
        service = self._service(vision)
        out = service.analyze(
            JPEG, "r.jpg", "image/jpeg", schemas.FuelTipoComprobante.remito_interno
        )
        # Borrar INTERNO despues del analyze
        self.db.delete(self.interno); self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            service.confirm_remito_interno(
                schemas.FuelRemitoInternoConfirmRequest(
                    upload_token=out["upload_token"],
                    fecha_carga=date(2026, 7, 30),
                    litros=Decimal("162"),
                    km_hora=Decimal("7153.1"),
                    equipo_id=1, paniol_id=1,
                    remito="0007222",
                ),
                self.empleado,
            )
        self.assertEqual(ctx.exception.status_code, 503)
        # No se creo ningun movimiento
        self.assertEqual(self.db.query(models.MovimientoCombustible).count(), 0)


if __name__ == "__main__":
    unittest.main()
