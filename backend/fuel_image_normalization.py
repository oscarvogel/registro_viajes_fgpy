"""Deterministic normalization for fuel image extractions.

Dos normalizadores: uno para ticket de estacion (INFONET, Petrobras,
Lider Express, etc.) y otro para el remito interno manuscrito de
Forestal Paraguay. La estructura es paralela a trip_image_normalization
pero con campos y reglas adaptadas al dominio combustible.

Reglas generales:
- Fechas en formato DD/MM/YYYY o DD/MM/YY. Completar el siglo a 20YY.
- Horas en HH:MM o HH:MM:SS.
- Litros y km con separador "." o ",", uno o mas decimales.
- Remito solo digitos; longitud esperada por tipo.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping


class FuelExtractionValidationError(ValueError):
    """Raised when extracted values cannot be normalized safely."""


_DIGITS_ONLY = re.compile(r"^\d+$")


@dataclass(frozen=True)
class NormalizedTicketExtraction:
    fecha: date
    hora: time | None
    litros: Decimal
    km_hora: int
    remito: str
    ruc: str | None
    razon_social_emisor: str | None
    producto: str | None
    nro_tarjeta: str | None


@dataclass(frozen=True)
class NormalizedRemitoInternoExtraction:
    fecha: date | None
    hora: time | None
    litros: Decimal
    kilometros: Decimal | None
    remito: str
    lugar_carga: str | None
    patente_observada: str | None
    firmante: str | None
    contacto: str | None
    tipo: str | None


def _parse_date_strict(value: Any, *, allow_two_digit_year: bool = True, optional: bool = False) -> date | None:
    """Acepta DD/MM/YYYY o DD/MM/YY. None o cualquier otro formato -> error.
    Si optional=True y el valor es None, devuelve None (en vez de error)."""
    if value is None:
        if optional:
            return None
        raise FuelExtractionValidationError("fecha invalida")
    if not isinstance(value, str) or not value.strip():
        if optional:
            return None
        raise FuelExtractionValidationError("fecha invalida")
    text = value.strip()
    patterns = (
        (r"^(\d{2})/(\d{2})/(\d{4})$", True),
        (r"^(\d{2})/(\d{2})/(\d{2})$", allow_two_digit_year),
    )
    for pattern, allow_short in patterns:
        m = re.fullmatch(pattern, text)
        if not m:
            continue
        d, mo, y = m.group(1), m.group(2), m.group(3)
        year = int(y)
        if allow_short and len(y) == 2:
            year = 2000 + year
        try:
            return date(year, int(mo), int(d))
        except ValueError:
            raise FuelExtractionValidationError("fecha invalida")
    raise FuelExtractionValidationError("fecha invalida")


def _parse_time_strict(value: Any) -> time | None:
    """Acepta HH:MM o HH:MM:SS. None -> None. Cualquier otra cosa -> error."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise FuelExtractionValidationError("hora invalida")
    text = value.strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise FuelExtractionValidationError("hora invalida")


def _parse_decimal(value: Any, *, field: str, allow_zero: bool = True) -> Decimal:
    """Convierte a Decimal. Acepta string con . o , como separador decimal.
    Si allow_zero=False, rechaza 0."""
    if value is None:
        raise FuelExtractionValidationError(f"{field} requerido")
    if isinstance(value, bool):
        raise FuelExtractionValidationError(f"{field} invalido")
    if isinstance(value, (int, float)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise FuelExtractionValidationError(f"{field} requerido")
    else:
        raise FuelExtractionValidationError(f"{field} invalido")
    # Reemplazar coma por punto solo si NO tiene ya un punto (caso miles europeo).
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    elif "," in text and "." in text:
        # Asumir coma como separador de miles: "1.234,56" -> 1234.56
        text = text.replace(".", "").replace(",", ".")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise FuelExtractionValidationError(f"{field} invalido") from exc
    if not result.is_finite() or result < 0:
        raise FuelExtractionValidationError(f"{field} invalido")
    if not allow_zero and result == 0:
        raise FuelExtractionValidationError(f"{field} debe ser mayor a 0")
    return result


def _parse_integer(value: Any, *, field: str, allow_zero: bool = True) -> int:
    """Convierte a int. Para km_hora (odometro sin decimales esperados)."""
    if value is None:
        raise FuelExtractionValidationError(f"{field} requerido")
    if isinstance(value, bool):
        raise FuelExtractionValidationError(f"{field} invalido")
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        if not math_isfinite(value):
            raise FuelExtractionValidationError(f"{field} invalido")
        result = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise FuelExtractionValidationError(f"{field} requerido")
        if not _DIGITS_ONLY.fullmatch(text):
            raise FuelExtractionValidationError(f"{field} invalido")
        result = int(text)
    else:
        raise FuelExtractionValidationError(f"{field} invalido")
    if result < 0 or (not allow_zero and result == 0):
        raise FuelExtractionValidationError(f"{field} invalido")
    return result


def math_isfinite(x: float) -> bool:
    return x == x and x not in (float("inf"), float("-inf"))


def _parse_remito(value: Any, *, expected_length: int, field: str = "remito") -> str:
    """Remito: solo digitos, longitud exacta. Para el remito interno manuscrito
    se permite variacion de 6-7 digitos (letra ambigua).

    Acepta un prefijo de una letra (tipica del formato INFONET, ej. "C-001-123"
    se imprime como "C001123" en el ticket). El prefijo se descarta y se valida
    solo la parte numerica. Tambien acepta separadores "-" o espacios.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise FuelExtractionValidationError(f"{field} requerido")
    if not isinstance(value, str):
        raise FuelExtractionValidationError(f"{field} invalido")
    text = value.strip()
    # Quitar prefijo de 1 letra seguido opcionalmente de "-" o espacio
    # (formato INFONET paraguayo: C-001-123 o C001123)
    text = re.sub(r"^[A-Za-z][\s-]?", "", text)
    # Quitar separadores "-" y espacios que puedan quedar
    text = re.sub(r"[\s-]", "", text)
    if not _DIGITS_ONLY.fullmatch(text):
        raise FuelExtractionValidationError(f"{field} debe ser solo digitos")
    accepted = (expected_length,) if isinstance(expected_length, int) else tuple(expected_length)
    if len(text) not in accepted:
        accepted_str = " o ".join(str(x) for x in accepted)
        raise FuelExtractionValidationError(
            f"{field} debe tener {accepted_str} digitos, recibio {len(text)}"
        )
    return text


def _clean_ruc(value: Any) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    # Acepta formato XXXXXXXX-Y o XXXXXXXX/Y; conserva separador.
    m = re.fullmatch(r"^(\d{6,8})([-/])(\d{1,2})$", text)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    # Cualquier otro formato con al menos 6 digitos consecutivos.
    digits = re.sub(r"\D", "", text)
    if len(digits) < 6:
        return None
    return digits


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _clean_patente(value: Any) -> str | None:
    text = _clean_optional_text(value)
    if text is None:
        return None
    # Solo letras y digitos, uppercase, longitud 6-7.
    cleaned = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    if not 6 <= len(cleaned) <= 7:
        return None
    return cleaned


def normalize_ticket_extraction(data: Mapping[str, Any]) -> NormalizedTicketExtraction:
    """Valida y normaliza la extraccion OCR de un ticket de estacion.

    - Rechaza litros=0, km_hora=0, fecha invalida, remito con longitud
      distinta de 7, RUC con formato no paraguayo.
    - Devuelve NormalizedTicketExtraction o lanza FuelExtractionValidationError.
    """
    fecha = _parse_date_strict(data.get("fecha"))
    hora = _parse_time_strict(data.get("hora"))
    litros = _parse_decimal(data.get("litros"), field="litros", allow_zero=False)
    km_hora = _parse_integer(data.get("km_hora"), field="km_hora", allow_zero=False)
    remito = _parse_remito(data.get("remito"), expected_length=7)
    ruc = _clean_ruc(data.get("ruc_emisor"))
    razon_social = _clean_optional_text(data.get("razon_social_emisor"))
    producto = _clean_optional_text(data.get("producto"))
    nro_tarjeta = _clean_optional_text(data.get("nro_tarjeta"))
    return NormalizedTicketExtraction(
        fecha=fecha,
        hora=hora,
        litros=litros,
        km_hora=km_hora,
        remito=remito,
        ruc=ruc,
        razon_social_emisor=razon_social,
        producto=producto,
        nro_tarjeta=nro_tarjeta,
    )


def normalize_remito_interno_extraction(data: Mapping[str, Any]) -> NormalizedRemitoInternoExtraction:
    """Valida y normaliza la extraccion OCR de un remito interno manuscrito.

    - Acepta fecha nula (campo manuscrito a veces ilegible); se devuelve None
      y se agrega un warning para que el operador la complete manualmente.
    - Acepta kilometros nulo (campo manuscrito a veces ilegible).
    - Campos de texto (lugar, patente, firmante, contacto, tipo) son
      opcionales: null si el OCR no los leyó.
    """
    fecha = _parse_date_strict(data.get("fecha"), optional=True)
    hora = _parse_time_strict(data.get("hora"))
    litros = _parse_decimal(data.get("litros"), field="litros", allow_zero=False)
    kilometros_raw = data.get("kilometros")
    kilometros: Decimal | None
    if kilometros_raw is None or (isinstance(kilometros_raw, str) and not kilometros_raw.strip()):
        kilometros = None
    else:
        kilometros = _parse_decimal(kilometros_raw, field="kilometros", allow_zero=True)
    remito = _parse_remito(data.get("remito"), expected_length=(6, 7))
    lugar = _clean_optional_text(data.get("lugar_carga"))
    patente = _clean_patente(data.get("patente_observada"))
    firmante = _clean_optional_text(data.get("firmante"))
    contacto = _clean_optional_text(data.get("contacto"))
    tipo = _clean_optional_text(data.get("tipo"))
    return NormalizedRemitoInternoExtraction(
        fecha=fecha,
        hora=hora,
        litros=litros,
        kilometros=kilometros,
        remito=remito,
        lugar_carga=lugar,
        patente_observada=patente,
        firmante=firmante,
        contacto=contacto,
        tipo=tipo,
    )
