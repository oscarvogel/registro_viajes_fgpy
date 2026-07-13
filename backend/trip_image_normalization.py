"""Deterministic normalization for trip data extracted from document images."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import Any, Mapping


_TONNE_QUANTUM = Decimal("0.001")
_WEIGHT_TOLERANCE = Decimal("0.010")
_FULL_REMITO = re.compile(r"^(\d{3})-(\d{3})-(\d{7})$")


class ExtractionValidationError(ValueError):
    """Raised when extracted values cannot be normalized safely."""


@dataclass(frozen=True)
class NormalizedExtraction:
    fecha_remision: date
    numero_remision_fpv: str
    peso_bruto_destino: Decimal
    tara_destino: Decimal
    neto_destino: Decimal
    proveedor_normalizado: str


def normalize_provider_name(value: Any) -> str:
    """Return a comparison key without performing provider lookup."""
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
            if tuple(tokens[-len(suffix) :]) == suffix:
                del tokens[-len(suffix) :]
                removed = True
                break
    return " ".join(tokens)


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ExtractionValidationError("fecha de remision invalida")
    for format_string in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), format_string).date()
        except ValueError:
            continue
    raise ExtractionValidationError("fecha de remision invalida")


def _normalize_remito(data: Mapping[str, Any]) -> str:
    full = data.get("numero_remision_fpv")
    if full is not None:
        normalized_full = str(full).strip()
        if not _FULL_REMITO.fullmatch(normalized_full):
            raise ExtractionValidationError("numero de remito invalido")
        return normalized_full

    widths = (("remito_tipo", 3), ("remito_sucursal", 3), ("remito_numero", 7))
    normalized_parts = []
    for field, width in widths:
        raw = data.get(field)
        part = "" if raw is None else str(raw).strip()
        if not part.isdigit() or len(part) > width:
            raise ExtractionValidationError("partes del remito incompletas o invalidas")
        normalized_parts.append(part.zfill(width))
    return "-".join(normalized_parts)


def _decimal_kg(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ExtractionValidationError("peso invalido")
    text = str(value).strip().replace(" ", "")
    if not text:
        raise ExtractionValidationError("peso invalido")
    if "," in text and "." in text:
        if text.rfind(",") < text.rfind("."):
            text = text.replace(",", "")
        else:
            text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    elif re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    try:
        result = Decimal(text)
    except InvalidOperation as error:
        raise ExtractionValidationError("peso invalido") from error
    if not result.is_finite() or result < 0:
        raise ExtractionValidationError("peso negativo o no finito")
    return result


def _weight_in_tonnes(value: Any) -> Decimal:
    return _decimal_kg(value) / Decimal("1000")


def normalize_extraction(data: Mapping[str, Any]) -> NormalizedExtraction:
    """Validate OCR fields and convert explicitly declared kilograms to tonnes."""
    unit = data.get("unidad_peso")
    if not isinstance(unit, str) or unit.strip().lower() not in {"kg", "kgs"}:
        raise ExtractionValidationError("unidad de peso faltante o no soportada")

    bruto = _weight_in_tonnes(data.get("peso_bruto"))
    tara = _weight_in_tonnes(data.get("tara"))
    neto = _weight_in_tonnes(data.get("neto"))
    if abs((bruto - tara) - neto) > _WEIGHT_TOLERANCE:
        raise ExtractionValidationError("pesos inconsistentes: bruto - tara no coincide con neto")

    return NormalizedExtraction(
        fecha_remision=_parse_date(data.get("fecha_remision")),
        numero_remision_fpv=_normalize_remito(data),
        peso_bruto_destino=bruto.quantize(_TONNE_QUANTUM),
        tara_destino=tara.quantize(_TONNE_QUANTUM),
        neto_destino=neto.quantize(_TONNE_QUANTUM),
        proveedor_normalizado=normalize_provider_name(data.get("proveedor_candidato")),
    )
