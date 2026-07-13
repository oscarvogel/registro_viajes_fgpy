import math
import unittest
from datetime import date, datetime
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
        invalid_dates = (
            "07/13/2026",
            "2026/07/13",
            "2026-7-13",
            "13/7/2026",
            " 2026-07-13 ",
            date(2026, 7, 13),
            datetime(2026, 7, 13, 10, 30),
        )
        for invalid_date in invalid_dates:
            with self.subTest(value=invalid_date), self.assertRaisesRegex(
                ExtractionValidationError, "fecha"
            ):
                normalize_extraction(self.valid_data(fecha_remision=invalid_date))

    def test_normalizes_supported_kg_representations(self):
        representations = (
            ("49690", "17080", "32610"),
            ("49690,00", "17080,00", "32610,00"),
            ("49.690,00", "17.080,00", "32.610,00"),
            (49690, 17080, 32610),
            (Decimal("49690"), Decimal("17080"), Decimal("32610")),
            (49690.0, 17080.0, 32610.0),
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

    def test_rejects_whitespace_around_full_remito(self):
        data = self.valid_data()
        for key in ("remito_tipo", "remito_sucursal", "remito_numero"):
            data.pop(key)
        data["numero_remision_fpv"] = " 002-003-0003677 "
        with self.assertRaisesRegex(ExtractionValidationError, "remito"):
            normalize_extraction(data)

    def test_rejects_non_ascii_digits_in_full_remito(self):
        for remito in ("٠٠٢-٠٠٣-٠٠٠٣٦٧٧", "００２-００３-０００３６７７"):
            data = self.valid_data()
            for key in ("remito_tipo", "remito_sucursal", "remito_numero"):
                data.pop(key)
            data["numero_remision_fpv"] = remito
            with self.subTest(remito=remito), self.assertRaisesRegex(
                ExtractionValidationError, "remito"
            ):
                normalize_extraction(data)

    def test_rejects_non_ascii_digits_in_separate_remito_parts(self):
        for parts in (
            {"remito_tipo": "٢"},
            {"remito_sucursal": "３"},
            {"remito_numero": "٣٦٧٧"},
        ):
            with self.subTest(parts=parts), self.assertRaisesRegex(
                ExtractionValidationError, "remito"
            ):
                normalize_extraction(self.valid_data(**parts))

    def test_rejects_missing_or_unsupported_unit(self):
        for unit in (None, "", "kgs", "lb", "ton"):
            with self.subTest(unit=unit), self.assertRaisesRegex(
                ExtractionValidationError, "unidad"
            ):
                normalize_extraction(self.valid_data(unidad_peso=unit))

    def test_accepts_kg_with_case_and_outer_whitespace(self):
        self.assertEqual(
            normalize_extraction(self.valid_data(unidad_peso="  KG ")).neto_destino,
            Decimal("32.610"),
        )

    def test_rejects_non_paraguayan_or_ambiguous_string_weight_formats(self):
        invalid_weights = (
            "49,690.00",
            "4.969E4",
            "49..690",
            "49.69",
            "49.690.00",
            "49.690,0,0",
            "+49690",
            "49 690",
        )
        for weight in invalid_weights:
            with self.subTest(weight=weight), self.assertRaisesRegex(
                ExtractionValidationError, "peso"
            ):
                normalize_extraction(self.valid_data(peso_bruto=weight))

    def test_rejects_negative_and_non_finite_weights(self):
        for weight in ("-1", "NaN", "Infinity", math.inf, math.nan):
            with self.subTest(weight=weight), self.assertRaisesRegex(
                ExtractionValidationError, "peso"
            ):
                normalize_extraction(self.valid_data(peso_bruto=weight))

    def test_wraps_extreme_decimal_quantize_failure_as_domain_error(self):
        with self.assertRaises(ExtractionValidationError):
            normalize_extraction(
                self.valid_data(
                    peso_bruto=Decimal("2e100"),
                    tara=Decimal("1e100"),
                    neto=Decimal("1e100"),
                )
            )


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
