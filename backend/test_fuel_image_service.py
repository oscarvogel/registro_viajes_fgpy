"""Tests for fuel_image_service: analyze + confirm + auto-crear proveedor INTERNO."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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


SECRET = "test-secret-that-is-at-least-thirty-two-bytes-long"
JPEG = b"\xff\xd8\xff" + b"fuel-image"
NOW = datetime(2026, 7, 31, 12, tzinfo=timezone.utc)


def _build_ocr_response_for_ticket(**overrides) -> dict:
    base = {
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
    base.update(overrides)
    return base


def _build_ocr_response_for_remito(**overrides) -> dict:
    base = {
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
    base.update(overrides)
    return base


class FakeVision:
    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def analyze(self, image_path, prompt=None, schema=None):
        self.calls.append({"path": str(image_path), "schema": schema, "prompt": prompt})
        if self.error is not None:
            raise self.error
        return self.response


class FuelImageServiceAnalyzeTests(unittest.TestCase):
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

    def _service(self, vision: FakeVision) -> FuelImageService:
        return FuelImageService(
            self.db, self.storage, vision=vision, session_factory=self.Session
        )

    def _seed_empleado(self):
        emp = models.Empleado(
            id=1,
            nombre="Chofer",
            apellido="Test",
            email="c@t",
            telefono="",
            fecha_contratacion=datetime(2024, 1, 1).date(),
            activo=True,
            porcentaje=0.0,
        )
        self.db.add(emp)
        self.db.commit()
        return emp

    def _seed_equipo(self):
        eq = models.Equipo(
            id=1,
            descripcion="Scania",
            patente="AAXO300",
            nro_chasis="CHS1",
            nro_motor="MTR1",
            tipo_movil_id=4,
            movil_asociado=0,
            activo=True,
            ult_hr_km=0,
        )
        self.db.add(eq)
        self.db.commit()
        return eq

    def _seed_paniol(self):
        pn = models.Paniol(
            id=1, descripcion="Tanque 1", activo=True, unidad_negocio_id=1
        )
        self.db.add(pn)
        # Asegurar que la unidad de negocio existe
        if not self.db.get(models.UnidadNegocio, 1):
            self.db.add(models.UnidadNegocio(
                id=1, descripcion="Forestal", activo=True
            ))
        self.db.commit()
        return pn

    def _seed_interno(self):
        prv = models.Proveedor(
            razon_social="INTERNO FORESTAL PARAGUAY", activo=True
        )
        self.db.add(prv)
        self.db.commit()
        return prv

    def test_analyze_ticket_resolves_existing_proveedor_by_ruc(self):
        self._seed_empleado()
        prv = models.Proveedor(
            razon_social="PETROBRAS", cuit="80015646-0", activo=True
        )
        self.db.add(prv); self.db.commit()
        vision = FakeVision(response=_build_ocr_response_for_ticket())
        out = self._service(vision).analyze(
            JPEG, "ticket.jpg", "image/jpeg", schemas.FuelTipoComprobante.ticket
        )
        self.assertEqual(out["proposal"]["proveedor_id"], prv.id)
        self.assertEqual(out["proposal"]["proveedor_candidato"], "PETROBRAS")
        self.assertEqual(out["tipo"], "ticket")
        self.assertIn("upload_token", out)
        # Vision called with fuel schema
        self.assertIs(vision.calls[0]["schema"], FUEL_TICKET_SCHEMA)

    def test_analyze_ticket_auto_creates_proveedor_inactivo_for_new_ruc(self):
        self._seed_empleado()
        vision = FakeVision(response=_build_ocr_response_for_ticket())
        out = self._service(vision).analyze(
            JPEG, "ticket.jpg", "image/jpeg", schemas.FuelTipoComprobante.ticket
        )
        proveedor_id = out["proposal"]["proveedor_id"]
        self.assertIsNotNone(proveedor_id)
        prv = self.db.query(models.Proveedor).filter(models.Proveedor.id == proveedor_id).one()
        self.assertFalse(prv.activo)
        # El cuit se guarda normalizado a digitos para matching exacto.
        self.assertEqual(prv.cuit, "800156460")
        # Hay al menos un warning sobre el proveedor nuevo
        self.assertTrue(any("Proveedor nuevo" in w for w in out["proposal"]["warnings"]))

    def test_analyze_ticket_vision_error_propagates_and_no_db_changes(self):
        self._seed_empleado()
        vision = FakeVision(error=MiniMaxVisionError("vision fail"))
        with self.assertRaises(MiniMaxVisionError):
            self._service(vision).analyze(
                JPEG, "ticket.jpg", "image/jpeg", schemas.FuelTipoComprobante.ticket
            )
        # Ningun proveedor fue creado
        self.assertEqual(self.db.query(models.Proveedor).count(), 0)

    def test_analyze_remito_uses_interno_provider(self):
        self._seed_empleado()
        interno = self._seed_interno()
        vision = FakeVision(response=_build_ocr_response_for_remito())
        out = self._service(vision).analyze(
            JPEG, "remito.jpg", "image/jpeg", schemas.FuelTipoComprobante.remito_interno
        )
        self.assertEqual(out["proposal"]["proveedor_id"], interno.id)
        self.assertEqual(out["proposal"]["proveedor_nombre"], "INTERNO FORESTAL PARAGUAY")
        # Vision called with remito schema
        self.assertIs(vision.calls[0]["schema"], FUEL_REMITO_SCHEMA)

    def test_analyze_remito_fails_cleanly_when_interno_missing(self):
        self._seed_empleado()
        # No sembramos INTERNO.
        vision = FakeVision(response=_build_ocr_response_for_remito())
        with self.assertRaises(HTTPException) as ctx:
            self._service(vision).analyze(
                JPEG, "remito.jpg", "image/jpeg", schemas.FuelTipoComprobante.remito_interno
            )
        self.assertEqual(ctx.exception.status_code, 503)

    def test_analyze_ticket_invalid_litros_returns_422(self):
        self._seed_empleado()
        vision = FakeVision(response=_build_ocr_response_for_ticket(litros="0"))
        with self.assertRaises(HTTPException) as ctx:
            self._service(vision).analyze(
                JPEG, "ticket.jpg", "image/jpeg", schemas.FuelTipoComprobante.ticket
            )
        self.assertEqual(ctx.exception.status_code, 422)

    def test_analyze_remito_invalid_remito_returns_422(self):
        self._seed_empleado()
        self._seed_interno()
        vision = FakeVision(
            response=_build_ocr_response_for_remito(remito="12345")
        )
        with self.assertRaises(HTTPException) as ctx:
            self._service(vision).analyze(
                JPEG, "remito.jpg", "image/jpeg", schemas.FuelTipoComprobante.remito_interno
            )
        self.assertEqual(ctx.exception.status_code, 422)


class FuelImageServiceConfirmTests(unittest.TestCase):
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
            id=1,
            nombre="Chofer",
            apellido="Test",
            email="c@t",
            telefono="",
            fecha_contratacion=datetime(2024, 1, 1).date(),
            activo=True,
            porcentaje=0.0,
        )
        self.db.add(self.empleado)
        self.equipo = models.Equipo(
            id=1,
            descripcion="Scania",
            patente="AAXO300",
            nro_chasis="CHS1",
            nro_motor="MTR1",
            tipo_movil_id=4,
            movil_asociado=0,
            activo=True,
            ult_hr_km=0,
        )
        self.db.add(self.equipo)
        if not self.db.get(models.UnidadNegocio, 1):
            self.db.add(models.UnidadNegocio(
                id=1, descripcion="Forestal", activo=True
            ))
        self.paniol = models.Paniol(
            id=1, descripcion="Tanque 1", activo=True, unidad_negocio_id=1
        )
        self.db.add(self.paniol)
        self.interno = models.Proveedor(
            razon_social="INTERNO FORESTAL PARAGUAY", activo=True
        )
        self.db.add(self.interno)
        self.petrol = models.Proveedor(
            razon_social="PETROBRAS", cuit="80015646-0", activo=True
        )
        self.db.add(self.petrol)
        self.db.commit()

    def _service(self, vision=None) -> FuelImageService:
        return FuelImageService(
            self.db, self.storage, vision=vision, session_factory=self.Session
        )

    def _saved_token(self) -> str:
        saved = self.storage.save_temp(JPEG, "ticket.jpg", "image/jpeg")
        return saved.token

    def test_confirm_ticket_creates_movimiento_and_imagen(self):
        token = self._saved_token()
        request = schemas.FuelTicketConfirmRequest(
            upload_token=token,
            fecha_carga=datetime(2026, 7, 30).date(),
            litros=430,
            km_hora=3362,
            equipo_id=1,
            paniol_id=1,
            proveedor_id=self.petrol.id,
            remito="9938226",
            observaciones="OK",
        )
        out = self._service().confirm_ticket(request, self.empleado)
        self.assertIn("movimiento_id", out)
        self.assertIn("imagen_id", out)
        mov = self.db.get(models.MovimientoCombustible, out["movimiento_id"])
        self.assertEqual(mov.remito, "9938226")
        self.assertEqual(mov.equipo_id, 1)
        self.assertEqual(mov.paniol_id, 1)
        self.assertEqual(mov.usuario, "1")
        img = self.db.get(models.CombustibleImagen, out["imagen_id"])
        self.assertEqual(img.movimiento_id, mov.id)

    def test_confirm_ticket_idempotent_returns_same_result(self):
        token = self._saved_token()
        request = schemas.FuelTicketConfirmRequest(
            upload_token=token,
            fecha_carga=datetime(2026, 7, 30).date(),
            litros=430,
            km_hora=3362,
            equipo_id=1,
            paniol_id=1,
            proveedor_id=self.petrol.id,
            remito="9938226",
        )
        service = self._service()
        first = service.confirm_ticket(request, self.empleado)
        second = service.confirm_ticket(request, self.empleado)
        self.assertEqual(first, second)
        self.assertEqual(
            self.db.query(models.MovimientoCombustible).count(), 1
        )

    def test_confirm_remito_interno_forces_interno_id(self):
        token = self._saved_token()
        request = schemas.FuelRemitoInternoConfirmRequest(
            upload_token=token,
            fecha_carga=datetime(2026, 7, 30).date(),
            litros=162,
            km_hora=7153.1,
            equipo_id=1,
            paniol_id=1,
            remito="0007222",
            observaciones="Tipo: INTERNO/GASOIL",
        )
        out = self._service().confirm_remito_interno(request, self.empleado)
        mov = self.db.get(models.MovimientoCombustible, out["movimiento_id"])
        # El provider_id debe ser el INTERNO, no el PETROL.
        self.assertEqual(mov.proveedor_id, self.interno.id)
        self.assertNotEqual(mov.proveedor_id, self.petrol.id)

    def test_confirm_remito_interno_fails_503_when_interno_missing(self):
        # Borramos el INTERNO.
        self.db.delete(self.interno); self.db.commit()
        token = self._saved_token()
        request = schemas.FuelRemitoInternoConfirmRequest(
            upload_token=token,
            fecha_carga=datetime(2026, 7, 30).date(),
            litros=162,
            km_hora=7153.1,
            equipo_id=1,
            remito="0007222",
        )
        with self.assertRaises(HTTPException) as ctx:
            self._service().confirm_remito_interno(request, self.empleado)
        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
