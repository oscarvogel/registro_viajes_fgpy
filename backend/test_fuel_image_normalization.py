"""Tests for fuel_image_normalization: 2 normalizadores (ticket + remito interno)."""
from __future__ import annotations

import unittest
from datetime import date, time
from decimal import Decimal

from fuel_image_normalization import (
    FuelExtractionValidationError,
    normalize_remito_interno_extraction,
    normalize_ticket_extraction,
)


class TicketNormalizationTests(unittest.TestCase):
    def _valid(self) -> dict:
        return {
            "fecha": "30/07/2026",
            "hora": "13:30:56",
            "litros": "430",
            "km_hora": "3362",
            "remito": "9938226",
            "ruc_emisor": "80015646-0",
            "razon_social_emisor": "PETROBRAS",
            "producto": "DIESEL EURO 5 S-50",
            "nro_tarjeta": "7002650831010234",
        }

    def test_valid_ticket_passes(self):
        out = normalize_ticket_extraction(self._valid())
        self.assertEqual(out.fecha, date(2026, 7, 30))
        self.assertEqual(out.hora, time(13, 30, 56))
        self.assertEqual(out.litros, Decimal("430"))
        self.assertEqual(out.km_hora, 3362)
        self.assertEqual(out.remito, "9938226")
        self.assertEqual(out.ruc, "80015646-0")
        self.assertEqual(out.razon_social_emisor, "PETROBRAS")
        self.assertEqual(out.producto, "DIESEL EURO 5 S-50")
        self.assertEqual(out.nro_tarjeta, "7002650831010234")

    def test_short_year_completed_to_20yy(self):
        data = self._valid()
        data["fecha"] = "30/07/26"
        out = normalize_ticket_extraction(data)
        self.assertEqual(out.fecha, date(2026, 7, 30))

    def test_missing_hora_is_optional(self):
        data = self._valid()
        data["hora"] = None
        out = normalize_ticket_extraction(data)
        self.assertIsNone(out.hora)

    def test_litros_zero_rejected(self):
        data = self._valid()
        data["litros"] = "0"
        with self.assertRaises(FuelExtractionValidationError) as ctx:
            normalize_ticket_extraction(data)
        self.assertIn("litros", str(ctx.exception))

    def test_litros_string_with_comma(self):
        data = self._valid()
        data["litros"] = "20,5"
        out = normalize_ticket_extraction(data)
        self.assertEqual(out.litros, Decimal("20.5"))

    def test_litros_string_with_thousands_european(self):
        data = self._valid()
        data["litros"] = "1.234,56"
        out = normalize_ticket_extraction(data)
        self.assertEqual(out.litros, Decimal("1234.56"))

    def test_km_hora_zero_rejected(self):
        data = self._valid()
        data["km_hora"] = "0"
        with self.assertRaises(FuelExtractionValidationError):
            normalize_ticket_extraction(data)

    def test_remito_wrong_length_rejected(self):
        data = self._valid()
        data["remito"] = "12345"  # 5 digitos
        with self.assertRaises(FuelExtractionValidationError) as ctx:
            normalize_ticket_extraction(data)
        self.assertIn("7 digitos", str(ctx.exception))

    def test_remito_with_letters_rejected(self):
        data = self._valid()
        data["remito"] = "9938A26"
        with self.assertRaises(FuelExtractionValidationError):
            normalize_ticket_extraction(data)

    def test_ruc_with_slash_separator_accepted(self):
        data = self._valid()
        data["ruc_emisor"] = "80073986/8"
        out = normalize_ticket_extraction(data)
        self.assertEqual(out.ruc, "80073986/8")

    def test_ruc_with_short_digits_returns_none(self):
        data = self._valid()
        data["ruc_emisor"] = "12345"
        out = normalize_ticket_extraction(data)
        self.assertIsNone(out.ruc)

    def test_missing_required_field_rejected(self):
        data = self._valid()
        data["remito"] = None
        with self.assertRaises(FuelExtractionValidationError) as ctx:
            normalize_ticket_extraction(data)
        self.assertIn("remito", str(ctx.exception).lower())

    def test_invalid_date_format_rejected(self):
        data = self._valid()
        data["fecha"] = "2026-07-30"  # formato ISO no soportado en DD/MM
        with self.assertRaises(FuelExtractionValidationError):
            normalize_ticket_extraction(data)

    def test_invalid_time_rejected(self):
        data = self._valid()
        data["hora"] = "13:30:99"
        with self.assertRaises(FuelExtractionValidationError):
            normalize_ticket_extraction(data)


class RemitoInternoNormalizationTests(unittest.TestCase):
    def _valid(self) -> dict:
        return {
            "fecha": "30/07/26",
            "hora": "13:42",
            "litros": "162",
            "kilometros": "7153.1",
            "remito": "0007222",
            "lugar_carga": "Gsibg",
            "patente_observada": "AAXO 300",
            "firmante": "Fernando",
            "contacto": "nambiarifernando@forestalparaguay.com.ar",
            "tipo": "INTERNO/GASOIL",
        }

    def test_valid_remito_passes(self):
        out = normalize_remito_interno_extraction(self._valid())
        self.assertEqual(out.fecha, date(2026, 7, 30))
        self.assertEqual(out.hora, time(13, 42))
        self.assertEqual(out.litros, Decimal("162"))
        self.assertEqual(out.kilometros, Decimal("7153.1"))
        self.assertEqual(out.remito, "0007222")
        self.assertEqual(out.lugar_carga, "Gsibg")
        self.assertEqual(out.patente_observada, "AAXO300")
        self.assertEqual(out.firmante, "Fernando")
        self.assertEqual(out.tipo, "INTERNO/GASOIL")

    def test_kilometros_optional(self):
        data = self._valid()
        data["kilometros"] = None
        out = normalize_remito_interno_extraction(data)
        self.assertIsNone(out.kilometros)

    def test_kilometros_zero_allowed(self):
        data = self._valid()
        data["kilometros"] = "0"
        out = normalize_remito_interno_extraction(data)
        self.assertEqual(out.kilometros, Decimal("0"))

    def test_litros_zero_rejected(self):
        data = self._valid()
        data["litros"] = "0"
        with self.assertRaises(FuelExtractionValidationError):
            normalize_remito_interno_extraction(data)

    def test_remito_wrong_length_rejected(self):
        data = self._valid()
        data["remito"] = "12345"  # 5 digitos fuera de rango
        with self.assertRaises(FuelExtractionValidationError) as ctx:
            normalize_remito_interno_extraction(data)
        self.assertIn("digitos", str(ctx.exception).lower())

    def test_remito_six_digits_accepted(self):
        data = self._valid()
        data["remito"] = "123456"
        out = normalize_remito_interno_extraction(data)
        self.assertEqual(out.remito, "123456")

    def test_patente_with_short_format_returns_none(self):
        data = self._valid()
        data["patente_observada"] = "ABC"
        out = normalize_remito_interno_extraction(data)
        self.assertIsNone(out.patente_observada)

    def test_patente_with_long_format_returns_none(self):
        data = self._valid()
        data["patente_observada"] = "ABCDEFGHI"
        out = normalize_remito_interno_extraction(data)
        self.assertIsNone(out.patente_observada)

    def test_all_optional_fields_null_when_missing(self):
        data = self._valid()
        data["lugar_carga"] = None
        data["patente_observada"] = None
        data["firmante"] = None
        data["contacto"] = None
        data["tipo"] = None
        out = normalize_remito_interno_extraction(data)
        self.assertIsNone(out.lugar_carga)
        self.assertIsNone(out.patente_observada)
        self.assertIsNone(out.firmante)
        self.assertIsNone(out.contacto)
        self.assertIsNone(out.tipo)

    def test_invalid_date_rejected(self):
        data = self._valid()
        data["fecha"] = "30-07-2026"
        with self.assertRaises(FuelExtractionValidationError):
            normalize_remito_interno_extraction(data)


if __name__ == "__main__":
    unittest.main()
