"""Idempotent cleanup of trip-image evidence and orphan promotions."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from models import ViajeImagen


@dataclass(frozen=True)
class TripImageCleanupResult:
    expired_deleted: int = 0
    temp_deleted: int = 0
    orphan_deleted: int = 0
    invalid_promotions: int = 0
    errors: tuple[str, ...] = ()


def cleanup_trip_images(db, storage, now: datetime, orphan_grace: timedelta = timedelta(hours=24)) -> TripImageCleanupResult:
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("now must be timezone-aware UTC")
    if not isinstance(orphan_grace, timedelta) or orphan_grace < timedelta(0):
        raise ValueError("orphan_grace must be non-negative")
    errors = []
    expired_deleted = temp_deleted = orphan_deleted = invalid_promotions = 0
    try:
        temp_deleted = storage.cleanup_expired_temps(now)
    except Exception:
        errors.append("temp_cleanup")

    db_available = True
    try:
        expired = db.query(ViajeImagen).filter(ViajeImagen.expires_at <= now.replace(tzinfo=None)).all()
    except Exception:
        errors.append("database_query")
        expired = []
        db_available = False
    for evidence in expired:
        try:
            storage.delete_confirmed(evidence.storage_path)
        except Exception:
            errors.append("expired_storage_delete")
            continue
        try:
            deleted = db.query(ViajeImagen).filter(
                ViajeImagen.id == evidence.id,
                ViajeImagen.token_hash == evidence.token_hash,
                ViajeImagen.storage_path == evidence.storage_path,
            ).delete(synchronize_session=False)
            db.commit()
            expired_deleted += int(bool(deleted))
        except Exception:
            db.rollback()
            errors.append("expired_database_delete")

    try:
        scan = storage.enumerate_promotions()
        invalid_promotions = scan.invalid_count
    except Exception:
        errors.append("promotion_scan")
        scan = None
    if db_available and scan is not None:
        for promotion in scan.promotions:
            if promotion.confirmed_at > now - orphan_grace:
                continue
            try:
                exists = db.query(ViajeImagen.id).filter(ViajeImagen.token_hash == promotion.token_hash).first() is not None
            except Exception:
                errors.append("orphan_database_recheck")
                db_available = False
                break
            if exists:
                continue
            try:
                orphan_deleted += int(storage.delete_orphaned_promotion(promotion))
            except Exception:
                errors.append("orphan_storage_delete")
    return TripImageCleanupResult(expired_deleted, temp_deleted, orphan_deleted, invalid_promotions, tuple(errors))
