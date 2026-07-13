import math
import unittest
from decimal import Decimal

from backend.trip_image_normalization import (
    ExtractionValidationError,
    normalize_extraction,
    normalize_provider_name,
)


class NormalizeExtractionTests(unittest.TestCase):
    def valid_data(self, **overrides):
        data = {
            "fecha_remision": "13/07/2026",
            "remito_tipo": "2",
            "remito_sucursal": "3",
            "remito_numero": "3677",
            "peso_bruto": "49.690",
            "tara": "17.080",
            "neto": "32.610",
            "unidad_peso": "kg",
            "proveedor_candidato": "ALCOGREEN S.A.",
        }
        data.update(overrides)
        return data

    def test_normalizes_main_ocr_sample(self):
        result = normalize_extraction(self.valid_data())

        self.assertEqual(result.fecha_remision.isoformat(), "2026-07-13")
        self.assertEqual(result.numero_remision_fpv, "002-003-0003677")
        self.assertEqual(result.peso_bruto_destino, Decimal("49.690"))
        self.assertEqual(result.tara_destino, Decimal("17.080"))
        self.assertEqual(result.neto_destino, Decimal("32.610"))
        self.assertEqual(result.proveedor_normalizado, "alcogreen")

    def test_accepts_iso_date(self):
        result = normalize_extraction(self.valid_data(fecha_remision="2026-07-13"))
        self.assertEqual(result.fecha_remision.isoformat(), "2026-07-13")

    def test_rejects_unlisted_date_formats(self):
        with self.assertRaisesRegex(ExtractionValidationError, "fecha"):
            normalize_extraction(self.valid_data(fecha_remision="07/13/2026"))

    def test_normalizes_supported_kg_representations(self):
        representations = (
            ("49690", "17080", "32610"),
            ("49.690,00", "17.080,00", "32.610,00"),
            (49690, 17080, 32610),
            (Decimal("49690"), Decimal("17080"), Decimal("32610")),
        )
        for bruto, tara, neto in representations:
            with self.subTest(bruto=bruto):
                result = normalize_extraction(
                    self.valid_data(peso_bruto=bruto, tara=tara, neto=neto)
                )
                self.assertEqual(result.peso_bruto_destino, Decimal("49.690"))
                self.assertEqual(result.tara_destino, Decimal("17.080"))
                self.assertEqual(result.neto_destino, Decimal("32.610"))

    def test_quantizes_tonnes_to_three_decimals(self):
        result = normalize_extraction(
            self.valid_data(peso_bruto="49.690,4", tara="17.080,2", neto="32.610,2")
        )
        self.assertEqual(result.peso_bruto_destino, Decimal("49.690"))

    def test_accepts_weight_difference_at_tolerance(self):
        result = normalize_extraction(self.valid_data(neto="32.600"))
        self.assertEqual(result.neto_destino, Decimal("32.600"))

    def test_rejects_weight_difference_over_tolerance(self):
        with self.assertRaisesRegex(ExtractionValidationError, "inconsistentes"):
            normalize_extraction(self.valid_data(neto="32.599"))

    def test_checks_tolerance_before_quantizing_stored_tonnes(self):
        with self.assertRaisesRegex(ExtractionValidationError, "inconsistentes"):
            normalize_extraction(self.valid_data(neto="32.599,6"))

    def test_rejects_incomplete_or_invalid_remito_parts(self):
        invalid = (
            {"remito_tipo": "", "remito_sucursal": "3", "remito_numero": "3677"},
            {"remito_tipo": "1234", "remito_sucursal": "3", "remito_numero": "3677"},
            {"remito_tipo": "2", "remito_sucursal": "A3", "remito_numero": "3677"},
            {"remito_tipo": "2", "remito_sucursal": "3", "remito_numero": "12345678"},
        )
        for parts in invalid:
            with self.subTest(parts=parts), self.assertRaisesRegex(
                ExtractionValidationError, "remito"
            ):
                normalize_extraction(self.valid_data(**parts))

    def test_accepts_exact_full_remito(self):
        data = self.valid_data()
        for key in ("remito_tipo", "remito_sucursal", "remito_numero"):
            data.pop(key)
        data["numero_remision_fpv"] = "002-003-0003677"
        self.assertEqual(
            normalize_extraction(data).numero_remision_fpv, "002-003-0003677"
        )

    def test_rejects_non_exact_full_remito(self):
        data = self.valid_data()
        for key in ("remito_tipo", "remito_sucursal", "remito_numero"):
            data.pop(key)
        data["numero_remision_fpv"] = "02-003-0003677-extra"
        with self.assertRaisesRegex(ExtractionValidationError, "remito"):
            normalize_extraction(data)

    def test_rejects_missing_or_unsupported_unit(self):
        for unit in (None, "", "lb", "ton"):
            with self.subTest(unit=unit), self.assertRaisesRegex(
                ExtractionValidationError, "unidad"
            ):
                normalize_extraction(self.valid_data(unidad_peso=unit))

    def test_rejects_negative_and_non_finite_weights(self):
        for weight in ("-1", "NaN", "Infinity", math.inf, math.nan):
            with self.subTest(weight=weight), self.assertRaisesRegex(
                ExtractionValidationError, "peso"
            ):
                normalize_extraction(self.valid_data(peso_bruto=weight))


class ProviderNameNormalizationTests(unittest.TestCase):
    def test_removes_accents_punctuation_spacing_and_corporate_suffixes(self):
        variants = ("Alcogreen S.A.", "  ÁLCOGREEN,   S A  ", "Alcogreen S.A.S.")
        for value in variants:
            with self.subTest(value=value):
                self.assertEqual(normalize_provider_name(value), "alcogreen")

    def test_preserves_meaningful_name_words(self):
        self.assertEqual(
            normalize_provider_name("Forestal del Paraná S.R.L."),
            "forestal del parana",
        )


if __name__ == "__main__":
    unittest.main()
