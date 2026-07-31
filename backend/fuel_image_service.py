"""Transactional application service for fuel image evidence (combustible).

Replica el patron de trip_image_service.py:
- analyze: guarda la imagen temporal, llama a MiniMax con el prompt/schema
  adecuado, normaliza y resuelve proveedor.
- confirm: crea el MovimientoCombustible, asocia la CombustibleImagen y
  promueve la imagen a retencion definitiva. Idempotente via token_hash.

Usa el mismo ImageStorage (namespaces fisicos compartidos `tmp` y
`confirmed`); la separacion entre viaje y combustible es logica, via
las tablas viaje_imagenes y combustible_imagenes.

Convencion del proveedor INTERNO (ver backend/models.py):
- INTERNO se busca por nombre, no por id hardcodeado.
- Si no existe o hay mas de uno, get_internal_provider_id() lanza
  RuntimeError; el service propaga el error.
"""
from __future__ import annotations

import hashlib
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import models
import schemas
from image_storage import ImageStorage
from minimax_vision import (
    FUEL_TICKET_PROMPT,
    FUEL_REMITO_INTERNO_PROMPT,
    FUEL_TICKET_SCHEMA,
    FUEL_REMITO_SCHEMA,
    MiniMaxVisionError,
    MiniMaxVisionClient,
    VisionSchema,
)
from fuel_image_normalization import (
    FuelExtractionValidationError,
    normalize_ticket_extraction,
    normalize_remito_interno_extraction,
)

from logger import app_logger


def _normalize_ruc(ruc: str | None) -> str:
    """Quita separadores y deja solo digitos, para matching exacto."""
    if not ruc:
        return ""
    return "".join(ch for ch in str(ruc) if ch.isdigit())


def _resolve_or_create_proveedor_by_ruc(
    db,
    ruc: str | None,
    razon_social: str | None,
) -> tuple[int | None, list[str]]:
    """Busca un proveedor por RUC normalizado. Si no existe, crea uno
    inactivo. Devuelve (id, warnings). id es None si el RUC es vacio.
    """
    if not ruc:
        return None, ["RUC no visible en el comprobante; revisar manualmente"]
    matches = (
        db.query(models.Proveedor)
        .filter(models.Proveedor.cuit.isnot(None))
        .all()
    )
    for proveedor in matches:
        if _normalize_ruc(proveedor.cuit) == ruc:
            return proveedor.id, []
    nuevo = models.Proveedor(
        razon_social=(razon_social or f"PROVEEDOR RUC {ruc}")[:100],
        cuit=ruc[:20],
        activo=False,
        observaciones="Creado por OCR de ticket de combustible. Revisar y activar manualmente.",
    )
    db.add(nuevo)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(models.Proveedor)
            .filter(models.Proveedor.cuit == ruc[:20])
            .first()
        )
        if existing:
            return existing.id, []
        raise
    return nuevo.id, [
        f"Proveedor nuevo (inactivo) creado por RUC {ruc}. "
        "Revisalo y activalo desde el panel de proveedores."
    ]


def _map_product_to_tipo_combustible(
    db, producto: str | None
) -> int | None:
    """Mapea la descripcion del producto OCR a un id del catalogo.

    Si el catalogo no tiene una entrada razonable, devuelve None y deja
    que el frontend elija.
    """
    if not producto:
        return None
    text = unicodedata.normalize("NFKD", producto.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    is_diesel = "diesel" in text or "gasoil" in text or "euro" in text
    is_nafta = "nafta" in text or "gasoline" in text or "grid" in text
    if not is_diesel and not is_nafta:
        return None
    # El catalogo real de tipos de combustible no esta expuesto por SQLAlchemy
    # en este codigo legacy; usamos una constante razonable.
    return 1 if is_diesel else 2


class FuelImageService:
    def __init__(self, db, storage: ImageStorage, vision: MiniMaxVisionClient | None = None, *, session_factory=None):
        self.db = db
        self.storage = storage
        self.vision = vision
        self.session_factory = session_factory or (
            sessionmaker(bind=db.get_bind()) if hasattr(db, "get_bind") else None
        )

    def analyze(
        self,
        data: bytes,
        original_name: str,
        mime_type: str,
        tipo: schemas.FuelTipoComprobante,
    ) -> dict[str, Any]:
        if self.vision is None:
            raise RuntimeError("Vision dependency is required for image analysis")
        if tipo is schemas.FuelTipoComprobante.ticket:
            prompt = FUEL_TICKET_PROMPT
            schema = FUEL_TICKET_SCHEMA
        else:
            prompt = FUEL_REMITO_INTERNO_PROMPT
            schema = FUEL_REMITO_SCHEMA
        temporary = self.storage.save_temp(data, original_name, mime_type)
        # Si MiniMax falla, el temporal queda para el cleanup diario
        # (mismo comportamiento que trip_image_service). No rompemos el
        # flujo por un error de OCR; el operador puede reintentar.
        raw = self.vision.analyze(
            self.storage.resolve_temp(temporary.token).path,
            prompt=prompt,
            schema=schema,
        )

        warnings = list(raw.get("warnings", []))

        if tipo is schemas.FuelTipoComprobante.ticket:
            return self._build_ticket_proposal(temporary.token, raw, warnings)
        return self._build_remito_proposal(temporary.token, raw, warnings)

    def _build_ticket_proposal(self, token: str, raw: dict, warnings: list[str]) -> dict:
        try:
            normalized = normalize_ticket_extraction(raw)
        except FuelExtractionValidationError as exc:
            raise HTTPException(422, f"Extraccion OCR del ticket invalida: {exc}")
        ruc_digits = _normalize_ruc(normalized.ruc)
        proveedor_id, prov_warnings = _resolve_or_create_proveedor_by_ruc(
            self.db, ruc_digits, normalized.razon_social_emisor
        )
        warnings.extend(prov_warnings)
        tipo_combustible_id = _map_product_to_tipo_combustible(
            self.db, normalized.producto
        )
        return {
            "upload_token": token,
            "tipo": schemas.FuelTipoComprobante.ticket.value,
            "proposal": {
                "fecha": normalized.fecha.isoformat(),
                "hora": normalized.hora.isoformat() if normalized.hora else None,
                "litros": str(normalized.litros),
                "km_hora": normalized.km_hora,
                "remito": normalized.remito,
                "ruc": normalized.ruc,
                "razon_social_emisor": normalized.razon_social_emisor,
                "producto": normalized.producto,
                "nro_tarjeta": normalized.nro_tarjeta,
                "proveedor_id": proveedor_id,
                "proveedor_candidato": normalized.razon_social_emisor,
                "tipo_combustible_id": tipo_combustible_id,
                "warnings": warnings,
            },
        }

    def _build_remito_proposal(self, token: str, raw: dict, warnings: list[str]) -> dict:
        try:
            normalized = normalize_remito_interno_extraction(raw)
        except FuelExtractionValidationError as exc:
            raise HTTPException(422, f"Extraccion OCR del remito interno invalida: {exc}")
        try:
            interno = models.get_internal_provider_id(self.db)
        except RuntimeError as exc:
            raise HTTPException(503, f"Proveedor INTERNO no disponible: {exc}")
        interno_obj = (
            self.db.query(models.Proveedor)
            .filter(models.Proveedor.id == interno)
            .one_or_none()
        )
        interno_nombre = interno_obj.razon_social if interno_obj else "INTERNO"
        tipo_combustible_id = None
        if normalized.tipo and "gasoil" in normalized.tipo.lower():
            tipo_combustible_id = 1
        elif normalized.tipo and "nafta" in normalized.tipo.lower():
            tipo_combustible_id = 2
        return {
            "upload_token": token,
            "tipo": schemas.FuelTipoComprobante.remito_interno.value,
            "proposal": {
                "fecha": normalized.fecha.isoformat(),
                "hora": normalized.hora.isoformat() if normalized.hora else None,
                "litros": str(normalized.litros),
                "kilometros": str(normalized.kilometros) if normalized.kilometros is not None else None,
                "remito": normalized.remito,
                "lugar_carga": normalized.lugar_carga,
                "patente_observada": normalized.patente_observada,
                "firmante": normalized.firmante,
                "contacto": normalized.contacto,
                "tipo": normalized.tipo,
                "proveedor_id": interno,
                "proveedor_nombre": interno_nombre,
                "tipo_combustible_id": tipo_combustible_id,
                "warnings": warnings,
            },
        }

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _compensate(self, token: str, promoted) -> None:
        if promoted is None:
            return
        try:
            self.storage.revert_promotion(token, promoted)
        except Exception:
            app_logger.exception("No se pudo compensar una promocion de imagen", exc_info=False)

    def _reconcile(self, token_hash_value: str, current_user) -> dict | None:
        if self.session_factory is None:
            raise RuntimeError("Session factory is required for confirmation reconciliation")
        fresh = self.session_factory()
        try:
            existing = (
                fresh.query(models.CombustibleImagen)
                .filter(models.CombustibleImagen.token_hash == token_hash_value)
                .first()
            )
            if not existing:
                return None
            if existing.movimiento is None or existing.movimiento.usuario != str(current_user.id):
                raise HTTPException(403, "Evidencia perteneciente a otro usuario")
            return {
                "movimiento_id": existing.movimiento_id,
                "imagen_id": existing.id,
            }
        finally:
            fresh.close()

    def _build_movimiento(
        self,
        *,
        fecha,
        litros,
        km_hora,
        equipo_id,
        paniol_id,
        proveedor_id,
        remito,
        observaciones,
        usuario,
        tipo_combustible_id,
    ) -> models.MovimientoCombustible:
        # Resolver unidad_negocio_id desde el paniol si lo hay.
        unidad_negocio_id = 1
        if paniol_id is not None:
            paniol = (
                self.db.query(models.Paniol)
                .filter(models.Paniol.id == paniol_id)
                .one_or_none()
            )
            if paniol and paniol.unidad_negocio_id is not None:
                unidad_negocio_id = paniol.unidad_negocio_id
        periodo = f"{fecha.year}{fecha.month:02d}"
        return models.MovimientoCombustible(
            fecha=fecha,
            tipo_combustible_id=tipo_combustible_id or 1,
            equipo_id=equipo_id,
            km_hora=float(km_hora),
            precio_litro=0.0,
            ingreso=Decimal(litros) if isinstance(litros, (int, float, str)) else litros,
            egreso=0.0,
            unidad_negocio_id=unidad_negocio_id,
            paniol_id=paniol_id,
            remito=str(remito)[:12],
            idtabla=0,
            tabla="movimientocombustible",
            usuario=str(usuario),
            fecha_grabacion=datetime.now(),
            observaciones=observaciones,
            proveedor_id=proveedor_id,
            periodo=periodo,
            remito2="0",
        )

    def confirm_ticket(
        self,
        request: schemas.FuelTicketConfirmRequest,
        current_user,
    ) -> dict:
        token_hash_value = self.token_hash(request.upload_token)
        existing = (
            self.db.query(models.CombustibleImagen)
            .filter(models.CombustibleImagen.token_hash == token_hash_value)
            .first()
        )
        if existing:
            if existing.movimiento is None or existing.movimiento.usuario != str(current_user.id):
                raise HTTPException(403, "Evidencia perteneciente a otro usuario")
            return {
                "movimiento_id": existing.movimiento_id,
                "imagen_id": existing.id,
            }
        promoted = None
        try:
            token = self.storage.describe_token(request.upload_token)
            movimiento = self._build_movimiento(
                fecha=request.fecha_carga,
                litros=request.litros,
                km_hora=request.km_hora,
                equipo_id=request.equipo_id,
                paniol_id=request.paniol_id,
                proveedor_id=request.proveedor_id,
                remito=request.remito,
                observaciones=request.observaciones,
                usuario=current_user.id,
                tipo_combustible_id=request.tipo_combustible_id,
            )
            self.db.add(movimiento)
            self.db.flush()
            image = models.CombustibleImagen(
                movimiento_id=movimiento.id,
                storage_path="pending",
                original_name=token.original_name,
                mime_type=token.detected_mime,
                sha256=token.sha256,
                token_hash=token_hash_value,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                expires_at=token.expires_at.replace(tzinfo=None),
            )
            self.db.add(image)
            self.db.flush()
            promoted = self.storage.promote(request.upload_token, datetime.now(timezone.utc))
            image.storage_path = promoted.relative_path
            image.mime_type = promoted.detected_mime
            image.sha256 = promoted.sha256
            image.created_at = promoted.confirmed_at.replace(tzinfo=None)
            image.expires_at = promoted.expires_at.replace(tzinfo=None)
            result = {
                "movimiento_id": movimiento.id,
                "imagen_id": image.id,
            }
        except IntegrityError:
            self._compensate(request.upload_token, promoted)
            self.db.rollback()
            existing = self._reconcile(token_hash_value, current_user)
            if existing:
                return existing
            raise HTTPException(409, "Conflicto al guardar el movimiento de combustible")
        except Exception:
            self._compensate(request.upload_token, promoted)
            self.db.rollback()
            raise

        try:
            self.db.commit()
        except Exception as commit_error:
            try:
                self.db.rollback()
            except Exception:
                app_logger.exception("No se pudo revertir la sesion tras fallo de commit", exc_info=False)
            try:
                reconciled = self._reconcile(token_hash_value, current_user)
            except HTTPException:
                raise
            except Exception:
                app_logger.exception("No se pudo reconciliar el resultado del commit", exc_info=False)
                raise commit_error
            if reconciled:
                return reconciled
            self._compensate(request.upload_token, promoted)
            raise commit_error
        return result

    def confirm_remito_interno(
        self,
        request: schemas.FuelRemitoInternoConfirmRequest,
        current_user,
    ) -> dict:
        # Resolver INTERNO por nombre; falla con 503 si no esta disponible.
        try:
            interno_id = models.get_internal_provider_id(self.db)
        except RuntimeError as exc:
            raise HTTPException(503, f"Proveedor INTERNO no disponible: {exc}")
        # Forzar el id del INTERNO aunque el payload diga otra cosa.
        return self.confirm_ticket(
            schemas.FuelTicketConfirmRequest(
                upload_token=request.upload_token,
                fecha_carga=request.fecha_carga,
                hora_carga=request.hora_carga,
                litros=request.litros,
                km_hora=request.km_hora,
                equipo_id=request.equipo_id,
                paniol_id=request.paniol_id,
                proveedor_id=interno_id,
                tipo_combustible_id=request.tipo_combustible_id,
                remito=request.remito,
                observaciones=request.observaciones,
            ),
            current_user,
        )
