"""Transactional application service for trip image evidence."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, or_
from sqlalchemy.orm import sessionmaker

import models
import schemas
from image_storage import ImageStorage
from trip_image_normalization import normalize_extraction, normalize_provider_name
from trip_service import create_trip

from logger import app_logger


class TripImageService:
    def __init__(self, db, storage: ImageStorage, vision=None, *, session_factory=None):
        self.db, self.storage, self.vision = db, storage, vision
        self.session_factory = session_factory or (sessionmaker(bind=db.get_bind()) if hasattr(db, "get_bind") else None)

    def analyze(self, data: bytes, original_name: str, mime_type: str):
        if self.vision is None:
            raise RuntimeError("Vision dependency is required for image analysis")
        temporary = self.storage.save_temp(data, original_name, mime_type)
        raw = self.vision.analyze(self.storage.resolve_temp(temporary.token).path)
        normalized = normalize_extraction(raw)
        raw_tokens = re.findall(r"[^\W_]+", str(raw.get("proveedor_candidato") or ""), re.UNICODE)
        useful_tokens = [(normalize_provider_name(token), token) for token in raw_tokens]
        useful_tokens = [(key, token) for key, token in useful_tokens if key and key in normalized.proveedor_normalizado]
        candidates = []
        if useful_tokens:
            _, token = max(useful_tokens, key=lambda item: len(item[0]))
            candidates = self.db.query(models.Proveedor).filter(
                models.Proveedor.activo.is_(True),
                or_(func.lower(models.Proveedor.razon_social).contains(token.lower()), models.Proveedor.razon_social.contains(token)),
            ).all()
        matches = [row for row in candidates if normalize_provider_name(row.razon_social) == normalized.proveedor_normalizado]
        warnings = list(raw.get("warnings", []))
        provider_id = matches[0].id if len(matches) == 1 else None
        if not provider_id:
            warnings.append("Proveedor sin coincidencia activa unica; seleccione un proveedor para confirmar")
        return {"upload_token": temporary.token, "proposal": {
            "fecha_remision": normalized.fecha_remision,
            "numero_remision_fpv": normalized.numero_remision_fpv,
            "proveedor_id": provider_id,
            "proveedor_candidato": raw.get("proveedor_candidato"),
            "peso_bruto_destino": normalized.peso_bruto_destino,
            "tara_destino": normalized.tara_destino,
            "neto_destino": normalized.neto_destino,
            "patente_observada": raw.get("patente_observada"),
            "chofer_observado": raw.get("chofer_observado"),
            "confidence": raw.get("confidence", {}), "warnings": warnings,
        }}

    @staticmethod
    def token_hash(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _compensate(self, token, promoted):
        if promoted is None:
            return
        try:
            self.storage.revert_promotion(token, promoted)
        except Exception:
            # The signed receipt intentionally remains as the recovery record.
            app_logger.exception("No se pudo compensar una promocion de imagen", exc_info=False)

    def _reconcile(self, token_hash, current_user):
        if self.session_factory is None:
            raise RuntimeError("Session factory is required for confirmation reconciliation")
        fresh = self.session_factory()
        try:
            existing = fresh.query(models.ViajeImagen).filter(models.ViajeImagen.token_hash == token_hash).first()
            if not existing:
                return None
            if existing.viaje.empleado_id != current_user.id:
                raise HTTPException(403, "Evidencia perteneciente a otro usuario")
            return {"viaje_id": existing.viaje_id, "imagen_id": existing.id}
        finally:
            fresh.close()

    def confirm(self, request: schemas.TripImageConfirmRequest, current_user):
        token_hash = self.token_hash(request.upload_token)
        existing = self.db.query(models.ViajeImagen).filter(models.ViajeImagen.token_hash == token_hash).first()
        if existing:
            if existing.viaje.empleado_id != current_user.id:
                raise HTTPException(403, "Evidencia perteneciente a otro usuario")
            return {"viaje_id": existing.viaje_id, "imagen_id": existing.id}
        promoted = None
        try:
            token = self.storage.describe_token(request.upload_token)
            registro = schemas.RegistroViajeCreate(
                fecha_remision=request.fecha_remision, fecha_recepcion=request.fecha_recepcion,
                proveedor_id=request.proveedor_id, numero_remision="",
                numero_remision_fpv=request.numero_remision_fpv, cliente_id=None,
                chofer_id=current_user.id, patente=request.patente,
                unidad_negocio_id=request.unidad_negocio_id, pesaje_unico=True,
                peso_bruto_origen=0, tara_origen=0, neto_origen=0,
                peso_bruto_destino=request.peso_bruto_destino,
                tara_destino=request.tara_destino, neto_destino=request.neto_destino,
                observaciones=request.observaciones,
            )
            trip = create_trip(self.db, registro, current_user, commit=False)
            image = models.ViajeImagen(
                viaje_id=trip.id, storage_path="pending",
                original_name=token.original_name, mime_type=token.detected_mime,
                sha256=token.sha256, token_hash=token_hash,
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
            result = {"viaje_id": trip.id, "imagen_id": image.id}
        except IntegrityError:
            self._compensate(request.upload_token, promoted)
            self.db.rollback()
            existing = self._reconcile(token_hash, current_user)
            if existing:
                return existing
            raise HTTPException(409, "Conflicto al guardar el viaje")
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
                reconciled = self._reconcile(token_hash, current_user)
            except HTTPException:
                raise
            except Exception:
                app_logger.exception("No se pudo reconciliar el resultado del commit de imagen", exc_info=False)
                raise commit_error
            if reconciled:
                return reconciled
            self._compensate(request.upload_token, promoted)
            raise commit_error
        return result
