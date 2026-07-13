"""Idempotent cleanup of trip-image evidence and orphan promotions."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from models import ViajeImagen
from image_storage import ImageStoragePathError


@dataclass(frozen=True)
class TripImageCleanupResult:
    expired_deleted: int = 0
    temp_deleted: int = 0
    orphan_deleted: int = 0
    invalid_promotions: int = 0
    errors: tuple[str, ...] = ()


def cleanup_trip_images(db, storage, now: datetime, orphan_grace: timedelta = timedelta(hours=24)) -> TripImageCleanupResult:
    """Clean evidence under filesystem and database locks.

    Orphan safety relies on MySQL/InnoDB locking the unique ``token_hash`` row
    or its unique-index gap for ``SELECT ... FOR UPDATE`` until commit.
    """
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("now must be timezone-aware UTC")
    if not isinstance(orphan_grace, timedelta) or orphan_grace < timedelta(0):
        raise ValueError("orphan_grace must be non-negative")
    try:
        with storage.cleanup_lock():
            return _cleanup_locked(db, storage, now, orphan_grace)
    except ImageStoragePathError:
        return TripImageCleanupResult(errors=("cleanup_lock",))


def _cleanup_locked(db, storage, now: datetime, orphan_grace: timedelta) -> TripImageCleanupResult:
    errors = []
    expired_deleted = temp_deleted = orphan_deleted = invalid_promotions = 0
    try:
        temp_deleted = storage.cleanup_expired_temps(now)
    except Exception:
        errors.append("temp_cleanup")

    db_available = True
    try:
        candidate_ids = [value[0] for value in db.query(ViajeImagen.id).filter(
            ViajeImagen.expires_at <= now.replace(tzinfo=None)
        ).all()]
    except Exception:
        errors.append("database_query")
        candidate_ids = []
        db_available = False
    try:
        scan = storage.enumerate_promotions()
        invalid_promotions = scan.invalid_count
        promotions_by_token = {item.token_hash: item for item in scan.promotions}
    except Exception:
        errors.append("promotion_scan")
        scan = None
        promotions_by_token = {}
    expired_tokens_deleted = set()
    for evidence_id in candidate_ids:
        try:
            evidence = db.query(ViajeImagen).filter(
                ViajeImagen.id == evidence_id,
                ViajeImagen.expires_at <= now.replace(tzinfo=None),
            ).with_for_update().one_or_none()
        except Exception:
            db.rollback()
            errors.append("expired_database_recheck")
            continue
        if evidence is None:
            db.rollback()
            continue
        evidence_token_hash = evidence.token_hash
        evidence_storage_path = evidence.storage_path
        try:
            storage.delete_confirmed(evidence_storage_path)
        except Exception:
            db.rollback()
            errors.append("expired_storage_delete")
            continue
        try:
            deleted = db.query(ViajeImagen).filter(
                ViajeImagen.id == evidence.id,
                ViajeImagen.token_hash == evidence_token_hash,
                ViajeImagen.storage_path == evidence_storage_path,
            ).delete(synchronize_session=False)
            db.commit()
            expired_deleted += int(bool(deleted))
            if deleted:
                expired_tokens_deleted.add(evidence_token_hash)
            if deleted and evidence_token_hash in promotions_by_token:
                try:
                    storage.delete_orphaned_promotion(promotions_by_token[evidence_token_hash])
                except Exception:
                    errors.append("expired_receipt_delete")
        except Exception:
            db.rollback()
            errors.append("expired_database_delete")

    if db_available and scan is not None:
        for promotion in scan.promotions:
            if promotion.token_hash in expired_tokens_deleted:
                continue
            if promotion.confirmed_at > now - orphan_grace:
                continue
            try:
                exists = db.query(ViajeImagen.id).filter(
                    ViajeImagen.token_hash == promotion.token_hash
                ).with_for_update().first() is not None
            except Exception:
                db.rollback()
                errors.append("orphan_database_recheck")
                db_available = False
                break
            if exists:
                db.rollback()
                continue
            try:
                orphan_deleted += int(storage.delete_orphaned_promotion(promotion))
                db.commit()
            except Exception:
                db.rollback()
                errors.append("orphan_storage_delete")
    return TripImageCleanupResult(expired_deleted, temp_deleted, orphan_deleted, invalid_promotions, tuple(errors))
