"""Tests for the fuel-image API endpoints (analyze, confirm, blob)."""
from __future__ import annotations

import asyncio
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
import schemas
from image_storage import ImageStorage
from minimax_vision import MiniMaxVisionError


SECRET = "fuel-api-test-secret-that-is-at-least-thirty-two-bytes"
JPEG = b"\xff\xd8\xff" + b"fuel-api-image"
NOW = datetime(2026, 7, 31, 12, tzinfo=timezone.utc)


def _ocr_ticket_response():
    return {
        "fecha": "30/07/2026", "hora": "13:30:56", "litros": "430",
        "km_hora": "3362", "remito": "9938226",
        "ruc_emisor": "80015646-0", "razon_social_emisor": "PETROBRAS",
        "producto": "DIESEL EURO 5 S-50", "nro_tarjeta": "7002650831010234",
        "confidence": {k: 0.9 for k in ["fecha", "hora", "litros", "km_hora", "remito", "ruc_emisor", "razon_social_emisor", "producto", "nro_tarjeta"]},
        "warnings": [],
    }


def _ocr_remito_response():
    return {
        "fecha": "30/07/26", "hora": "13:42", "litros": "162",
        "kilometros": "7153.1", "remito": "0007222",
        "lugar_carga": "Gsibg", "patente_observada": "AAXO300",
        "firmante": "Fernando", "contacto": "x@y",
        "tipo": "INTERNO/GASOIL",
        "confidence": {k: 0.7 for k in ["fecha", "hora", "litros", "kilometros", "remito", "lugar_carga", "patente_observada", "firmante", "contacto", "tipo"]},
        "warnings": [],
    }


class FuelImageEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.storage = ImageStorage(root=self.root, token_secret=SECRET, now=lambda: NOW)
        # Setear env vars para que get_fuel_image_storage() funcione sin env real
        import os
        os.environ["VIAJE_IMAGE_STORAGE_DIR"] = str(self.root)
        os.environ["IMAGE_TOKEN_SECRET"] = SECRET
        os.environ["MINIMAX_VISION_COMMAND"] = "echo stub"
        self.engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        # Sembrar lo minimo
        self.empleado = models.Empleado(
            id=1, nombre="C", apellido="T", email="c@t",
            fecha_contratacion=datetime(2024, 1, 1).date(),
            activo=True, porcentaje=0.0,
        )
        self.db.add(self.empleado)
        if not self.db.get(models.UnidadNegocio, 1):
            self.db.add(models.UnidadNegocio(id=1, descripcion="F", activo=True))
        self.db.add(models.Equipo(
            id=1, descripcion="S", patente="AAXO300",
            nro_chasis="C", nro_motor="M",
            tipo_movil_id=4, movil_asociado=0, activo=True, ult_hr_km=0,
        ))
        self.db.add(models.Paniol(
            id=1, descripcion="T1", activo=True, unidad_negocio_id=1
        ))
        self.db.add(models.Proveedor(
            razon_social="INTERNO FORESTAL PARAGUAY", activo=True
        ))
        self.db.add(models.Proveedor(
            razon_social="PETROBRAS", cuit="800156460", activo=True
        ))
        self.db.commit()

    def test_analyze_rejects_invalid_tipo(self):
        import main
        with patch("main.get_fuel_image_storage", return_value=self.storage):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(main.analyze_fuel_image(
                    file=_FakeUpload(), tipo="otro", current_user=self.empleado
                ))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_analyze_rejects_oversize(self):
        import main
        small_storage = ImageStorage(
            root=self.root, token_secret=SECRET, now=lambda: NOW, max_bytes=5
        )
        big = b"\xff\xd8\xff" + b"x" * 10  # 13 bytes, supera el max de 5
        with patch("main.get_fuel_image_storage", return_value=small_storage):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(main.analyze_fuel_image(
                    file=_FakeUpload(data=big), tipo="ticket", current_user=self.empleado
                ))
        self.assertEqual(ctx.exception.status_code, 413)

    def test_analyze_dispatches_to_worker_with_correct_args(self):
        import main
        captured = {}

        def worker(data, original_name, mime_type, tipo, storage, session_factory=None):
            captured["data_len"] = len(data)
            captured["name"] = original_name
            captured["mime"] = mime_type
            captured["tipo"] = tipo
            captured["storage"] = storage
            return {"upload_token": "t", "tipo": tipo.value, "proposal": {}}

        with patch("main.get_fuel_image_storage", return_value=self.storage), \
             patch("main.analyze_fuel_image_in_worker", side_effect=worker):
            asyncio.run(main.analyze_fuel_image(
                file=_FakeUpload(), tipo="ticket", current_user=self.empleado
            ))
        self.assertEqual(captured["data_len"], len(JPEG))
        self.assertEqual(captured["mime"], "image/jpeg")
        self.assertIs(captured["storage"], self.storage)

    def test_analyze_vision_error_returns_502(self):
        import main

        def worker(data, original_name, mime_type, tipo, storage, session_factory=None):
            raise MiniMaxVisionError("boom")

        with patch("main.get_fuel_image_storage", return_value=self.storage), \
             patch("main.analyze_fuel_image_in_worker", side_effect=worker):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(main.analyze_fuel_image(
                    file=_FakeUpload(), tipo="ticket", current_user=self.empleado
                ))
        self.assertEqual(ctx.exception.status_code, 502)

    def test_confirm_ticket_happy_path(self):
        import main
        with patch("main.get_fuel_image_storage", return_value=self.storage):
            token = self.storage.save_temp(JPEG, "t.jpg", "image/jpeg").token
            request = schemas.FuelTicketConfirmRequest(
                upload_token=token,
                fecha_carga=datetime(2026, 7, 30).date(),
                litros=430, km_hora=3362,
                equipo_id=1, paniol_id=1, proveedor_id=2, remito="9938226",
            )
            out = main.confirm_fuel_image_ticket(request, self.db, self.empleado)
            self.assertIn("movimiento_id", out)
            self.assertIn("imagen_id", out)
            self.assertEqual(self.db.query(models.MovimientoCombustible).count(), 1)

    def test_confirm_remito_interno_forces_interno_id(self):
        import main
        interno = self.db.query(models.Proveedor).filter(
            models.Proveedor.razon_social.ilike("%INTERNO%")
        ).one()
        with patch("main.get_fuel_image_storage", return_value=self.storage):
            token = self.storage.save_temp(JPEG, "r.jpg", "image/jpeg").token
            request = schemas.FuelRemitoInternoConfirmRequest(
                upload_token=token,
                fecha_carga=datetime(2026, 7, 30).date(),
                litros=162, km_hora=7153.1,
                equipo_id=1, paniol_id=1, remito="0007222",
            )
            out = main.confirm_fuel_image_remito_interno(request, self.db, self.empleado)
            mov = self.db.get(models.MovimientoCombustible, out["movimiento_id"])
            self.assertEqual(mov.proveedor_id, interno.id)


class _FakeUpload:
    def __init__(self, data: bytes = JPEG):
        self.filename = "t.jpg"
        self.content_type = "image/jpeg"

    async def read(self, size: int) -> bytes:
        return self.data if hasattr(self, "data") else JPEG


class FuelImageRouteRegistrationTests(unittest.TestCase):
    def test_routes_are_registered(self):
        import main
        routes = [
            (r.path, sorted(r.methods))
            for r in main.app.routes
            if hasattr(r, "methods") and "fuel" in r.path.lower()
        ]
        self.assertTrue(any("/analyze" in p for p, _ in routes))
        self.assertTrue(any("/confirm/ticket" in p for p, _ in routes))
        self.assertTrue(any("/confirm/remito-interno" in p for p, _ in routes))
        self.assertTrue(any("/blob" in p for p, _ in routes))


if __name__ == "__main__":
    unittest.main()
