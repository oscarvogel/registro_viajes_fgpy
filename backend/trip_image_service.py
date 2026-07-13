"""Transactional application service for trip image evidence."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

import models
import schemas
from image_storage import ImageStorage, ImageTokenError
from trip_image_normalization import normalize_extraction, normalize_provider_name
from trip_service import create_trip


class TripImageService:
    def __init__(self, db, storage: ImageStorage, vision):
        self.db, self.storage, self.vision = db, storage, vision

    def analyze(self, data: bytes, original_name: str, mime_type: str):
        temporary = self.storage.save_temp(data, original_name, mime_type)
        raw = self.vision.analyze(self.storage.resolve_temp(temporary.token).path)
        normalized = normalize_extraction(raw)
        matches = [row for row in self.db.query(models.Proveedor).filter(models.Proveedor.activo.is_(True)).all()
                   if normalize_provider_name(row.razon_social) == normalized.proveedor_normalizado]
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

    def confirm(self, request: schemas.TripImageConfirmRequest, current_user):
        token_hash = self.token_hash(request.upload_token)
        existing = self.db.query(models.ViajeImagen).filter(models.ViajeImagen.token_hash == token_hash).first()
        if existing:
            if existing.viaje.empleado_id != current_user.id:
                raise HTTPException(403, "Evidencia perteneciente a otro usuario")
            return {"viaje_id": existing.viaje_id, "imagen_id": existing.id}
        try:
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
            confirmed = self.storage.promote(request.upload_token, datetime.now(timezone.utc))
            payload = self.storage._verify_token(request.upload_token)
            image = models.ViajeImagen(
                viaje_id=trip.id, storage_path=confirmed.relative_path,
                original_name=payload["name"], mime_type=confirmed.detected_mime,
                sha256=confirmed.sha256, token_hash=token_hash,
                created_at=confirmed.confirmed_at.replace(tzinfo=None),
                expires_at=confirmed.expires_at.replace(tzinfo=None),
            )
            self.db.add(image); self.db.commit(); self.db.refresh(image)
            return {"viaje_id": trip.id, "imagen_id": image.id}
        except IntegrityError:
            self.db.rollback()
            existing = self.db.query(models.ViajeImagen).filter(models.ViajeImagen.token_hash == token_hash).first()
            if existing and existing.viaje.empleado_id == current_user.id:
                return {"viaje_id": existing.viaje_id, "imagen_id": existing.id}
            raise HTTPException(409, "La imagen ya fue confirmada")
        except Exception:
            self.db.rollback()
            raise
