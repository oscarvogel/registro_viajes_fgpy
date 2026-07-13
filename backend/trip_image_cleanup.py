"""Idempotent cleanup of trip-image evidence and orphan promotions."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import inspect, text
from models import ViajeImagen
from image_storage import ImageStoragePathError


@dataclass(frozen=True)
class TripImageCleanupResult:
    expired_deleted: int = 0
    temp_deleted: int = 0
    orphan_deleted: int = 0
    invalid_promotions: int = 0
    errors: tuple[str, ...] = ()


ORPHAN_GRACE = timedelta(hours=24)


def _matches_stored_naive_utc(stored: datetime, signed: datetime, *, seconds_precision: bool) -> bool:
    """Compare aware UTC receipt time at the precision retained by the DB."""
    if not isinstance(stored, datetime) or stored.tzinfo is not None:
        return False
    if signed.tzinfo is None or signed.utcoffset() != timedelta(0):
        return False
    expected = signed.replace(tzinfo=None)
    if seconds_precision:
        stored = stored.replace(microsecond=0)
        expected = expected.replace(microsecond=0)
    return stored == expected


def cleanup_trip_images(db, storage, now: datetime) -> TripImageCleanupResult:
    """Clean evidence under filesystem and database locks.

    On MySQL, orphan safety requires confirmed REPEATABLE READ or SERIALIZABLE
    isolation so InnoDB locks the unique ``token_hash`` row/index gap. SQLite
    uses BEGIN IMMEDIATE before the absent-token check to exclude writers.
    """
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("now must be timezone-aware UTC")
    try:
        with storage.cleanup_lock():
            return _cleanup_locked(db, storage, now)
    except ImageStoragePathError:
        return TripImageCleanupResult(errors=("cleanup_lock",))


def _cleanup_locked(db, storage, now: datetime) -> TripImageCleanupResult:
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
        db.rollback()
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
    try:
        evidence_seconds_precision = db.get_bind().dialect.name == "mysql"
    except Exception:
        evidence_seconds_precision = False
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
        promotion = promotions_by_token.get(evidence_token_hash)
        if (
            promotion is None
            or evidence_storage_path != promotion.relative_path
            or evidence.sha256 != promotion.sha256
            or evidence.mime_type != promotion.detected_mime
            or not _matches_stored_naive_utc(
                evidence.created_at, promotion.confirmed_at, seconds_precision=evidence_seconds_precision
            )
            or not _matches_stored_naive_utc(
                evidence.expires_at, promotion.expires_at, seconds_precision=evidence_seconds_precision
            )
        ):
            db.rollback()
            errors.append("expired_metadata_mismatch")
            continue
        try:
            storage.delete_confirmed_promotion(promotion)
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
        try:
            dialect = db.get_bind().dialect.name
            if dialect == "mysql":
                isolation = str(db.connection().get_isolation_level()).upper().replace("_", " ")
                orphan_isolation_safe = isolation in {"REPEATABLE READ", "SERIALIZABLE"}
                live_schema = inspect(db.get_bind())
                indexes = live_schema.get_indexes(ViajeImagen.__tablename__)
                constraints = live_schema.get_unique_constraints(ViajeImagen.__tablename__)
                orphan_unique_safe = any(
                    item.get("unique") is True and item.get("column_names") == ["token_hash"] for item in indexes
                ) or any(item.get("column_names") == ["token_hash"] for item in constraints)
            elif dialect == "sqlite":
                orphan_isolation_safe = True
                orphan_unique_safe = True
            else:
                orphan_isolation_safe = False
                orphan_unique_safe = False
        except Exception:
            orphan_isolation_safe = False
            orphan_unique_safe = False
        if not orphan_isolation_safe and scan.promotions:
            errors.append("orphan_isolation_unsafe")
        elif not orphan_unique_safe and scan.promotions:
            errors.append("orphan_unique_index_unsafe")
        for promotion in scan.promotions:
            if promotion.token_hash in expired_tokens_deleted:
                continue
            if promotion.confirmed_at > now - ORPHAN_GRACE:
                continue
            if not orphan_isolation_safe or not orphan_unique_safe:
                continue
            try:
                if dialect == "sqlite":
                    db.rollback()
                    db.execute(text("BEGIN IMMEDIATE"))
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
