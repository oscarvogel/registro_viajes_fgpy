import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from image_storage import ImageStorage
from image_storage import ImageStoragePathError
from trip_image_cleanup import cleanup_trip_images


NOW = datetime(2026, 7, 13, 12, tzinfo=timezone.utc)
SECRET = "cleanup-secret-that-is-at-least-thirty-two-bytes"
JPEG = b"\xff\xd8\xff" + b"cleanup-image"


class TripImageCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.storage = ImageStorage(root=self.root, token_secret=SECRET, now=lambda: NOW)
        self.engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def add_evidence(self, db, *, confirmed_at=NOW - timedelta(days=61), expires_at=None):
        saved = self.storage.save_temp(JPEG, "e.jpg", "image/jpeg")
        confirmed = self.storage.promote(saved.token, confirmed_at)
        row = models.ViajeImagen(
            viaje_id=999, storage_path=confirmed.relative_path, original_name="e.jpg",
            mime_type="image/jpeg", sha256=confirmed.sha256,
            token_hash=__import__("hashlib").sha256(saved.token.encode("ascii")).hexdigest(),
            created_at=confirmed_at.replace(tzinfo=None),
            expires_at=(expires_at or confirmed.expires_at).replace(tzinfo=None),
        )
        db.add(row); db.commit()
        return row, confirmed

    def test_expired_deleted_unexpired_retained_and_second_run_is_empty(self):
        db = self.Session()
        expired, expired_file = self.add_evidence(db)
        fresh, fresh_file = self.add_evidence(db, confirmed_at=NOW, expires_at=NOW + timedelta(days=60))
        expired_id, fresh_id = expired.id, fresh.id
        result = cleanup_trip_images(db, self.storage, NOW)
        self.assertEqual((result.expired_deleted, result.temp_deleted, result.orphan_deleted, result.errors), (1, 0, 0, ()))
        self.assertIsNone(db.get(models.ViajeImagen, expired_id))
        self.assertIsNotNone(db.get(models.ViajeImagen, fresh_id))
        self.assertFalse((self.root / expired_file.relative_path).exists())
        self.assertTrue((self.root / fresh_file.relative_path).exists())
        self.assertEqual(cleanup_trip_images(db, self.storage, NOW).expired_deleted, 0)

    def test_storage_failure_retains_metadata_and_continues(self):
        db = self.Session(); first, _ = self.add_evidence(db); second, _ = self.add_evidence(db)
        first_id, second_id = first.id, second.id
        real_delete = self.storage.delete_confirmed
        self.storage.delete_confirmed = Mock(side_effect=[OSError("secret path"), None])
        result = cleanup_trip_images(db, self.storage, NOW)
        self.assertEqual(result.expired_deleted, 1)
        self.assertEqual(result.errors, ("expired_storage_delete",))
        self.assertIsNotNone(db.get(models.ViajeImagen, first_id))
        self.assertIsNone(db.get(models.ViajeImagen, second_id))
        self.storage.delete_confirmed = real_delete

    def test_stale_expired_row_path_never_deletes_another_promotion(self):
        db = self.Session()
        first, first_file = self.add_evidence(db)
        second, second_file = self.add_evidence(
            db, confirmed_at=NOW - timedelta(days=2), expires_at=NOW + timedelta(days=58)
        )
        first.storage_path = second.storage_path
        db.commit()
        result = cleanup_trip_images(db, self.storage, NOW)
        self.assertIn("expired_metadata_mismatch", result.errors)
        self.assertIsNotNone(db.get(models.ViajeImagen, first.id))
        self.assertTrue((self.root / first_file.relative_path).exists())
        self.assertTrue((self.root / second_file.relative_path).exists())

    def test_old_orphan_deleted_recent_and_db_backed_retained(self):
        db = self.Session()
        old = self.storage.promote(self.storage.save_temp(JPEG, "old.jpg", "image/jpeg").token, NOW - timedelta(days=2))
        recent = self.storage.promote(self.storage.save_temp(JPEG, "recent.jpg", "image/jpeg").token, NOW - timedelta(hours=1))
        backed, backed_file = self.add_evidence(db, confirmed_at=NOW - timedelta(days=2), expires_at=NOW + timedelta(days=58))
        result = cleanup_trip_images(db, self.storage, NOW)
        self.assertEqual(result.orphan_deleted, 1)
        self.assertFalse((self.root / old.relative_path).exists())
        self.assertTrue((self.root / recent.relative_path).exists())
        self.assertTrue((self.root / backed_file.relative_path).exists())
        self.assertEqual(cleanup_trip_images(db, self.storage, NOW).orphan_deleted, 0)

    def test_db_recheck_failure_deletes_no_orphans(self):
        db = Mock()
        db.query.side_effect = RuntimeError("database details")
        promoted = self.storage.promote(self.storage.save_temp(JPEG, "old.jpg", "image/jpeg").token, NOW - timedelta(days=2))
        result = cleanup_trip_images(db, self.storage, NOW)
        self.assertIn("database_query", result.errors)
        self.assertEqual(result.orphan_deleted, 0)
        self.assertTrue((self.root / promoted.relative_path).exists())

    def test_requires_aware_utc_now(self):
        with self.assertRaises(ValueError):
            cleanup_trip_images(self.Session(), self.storage, NOW.replace(tzinfo=None))

    def test_cleanup_lock_timeout_is_safe_and_deletes_nothing(self):
        db = self.Session(); row, confirmed = self.add_evidence(db)
        other = ImageStorage(root=self.root, token_secret=SECRET, now=lambda: NOW, lock_timeout_seconds=0.02)
        with self.storage.cleanup_lock():
            result = cleanup_trip_images(db, other, NOW)
        self.assertEqual(result.errors, ("cleanup_lock",))
        self.assertEqual(result.expired_deleted, 0)
        self.assertIsNotNone(db.get(models.ViajeImagen, row.id))
        self.assertTrue((self.root / confirmed.relative_path).exists())

    def test_candidate_mutated_before_locked_reselect_does_not_delete_old_file(self):
        candidate_query = Mock()
        candidate_query.filter.return_value.all.return_value = [(7,)]
        locked_query = Mock()
        locked_query.filter.return_value.with_for_update.return_value.one_or_none.return_value = None
        db = Mock()
        db.query.side_effect = [candidate_query, locked_query]
        storage = Mock()
        storage.cleanup_lock.return_value.__enter__ = Mock(return_value=None)
        storage.cleanup_lock.return_value.__exit__ = Mock(return_value=False)
        storage.cleanup_expired_temps.return_value = 0
        storage.enumerate_promotions.return_value = Mock(promotions=(), invalid_count=0)
        result = cleanup_trip_images(db, storage, NOW)
        storage.delete_confirmed.assert_not_called()
        self.assertEqual(result.expired_deleted, 0)

    def test_orphan_is_retained_when_evidence_appears_before_locked_recheck(self):
        promoted = self.storage.promote(
            self.storage.save_temp(JPEG, "old.jpg", "image/jpeg").token,
            NOW - timedelta(days=2),
        )
        candidate_query = Mock()
        candidate_query.filter.return_value.all.return_value = []
        orphan_query = Mock()
        orphan_query.filter.return_value.with_for_update.return_value.first.return_value = (42,)
        db = Mock(); db.query.side_effect = [candidate_query, orphan_query]
        result = cleanup_trip_images(db, self.storage, NOW)
        self.assertEqual(result.orphan_deleted, 0)
        self.assertTrue((self.root / promoted.relative_path).exists())

    def test_mysql_read_committed_skips_orphan_deletion(self):
        promoted = self.storage.promote(self.storage.save_temp(JPEG, "old.jpg", "image/jpeg").token, NOW - timedelta(days=2))
        db = Mock()
        db.get_bind.return_value.dialect.name = "mysql"
        db.connection.return_value.get_isolation_level.return_value = "READ COMMITTED"
        candidates = Mock(); candidates.filter.return_value.all.return_value = []
        db.query.return_value = candidates
        result = cleanup_trip_images(db, self.storage, NOW)
        self.assertIn("orphan_isolation_unsafe", result.errors)
        self.assertEqual(result.orphan_deleted, 0)
        self.assertTrue((self.root / promoted.relative_path).exists())

    def test_mysql_repeatable_read_allows_locked_orphan_delete(self):
        promoted = self.storage.promote(self.storage.save_temp(JPEG, "old.jpg", "image/jpeg").token, NOW - timedelta(days=2))
        candidate_query = Mock(); candidate_query.filter.return_value.all.return_value = []
        orphan_query = Mock(); orphan_query.filter.return_value.with_for_update.return_value.first.return_value = None
        db = Mock(); db.query.side_effect = [candidate_query, orphan_query]
        db.get_bind.return_value.dialect.name = "mysql"
        db.connection.return_value.get_isolation_level.return_value = "REPEATABLE READ"
        result = cleanup_trip_images(db, self.storage, NOW)
        self.assertEqual(result.orphan_deleted, 1)
        self.assertFalse((self.root / promoted.relative_path).exists())


class SchedulerCleanupTests(unittest.TestCase):
    def test_registers_daily_cleanup_with_exact_safety_options(self):
        import scheduler
        fake = Mock()
        task = scheduler.TaskScheduler(scheduler=fake)
        with patch.dict(os.environ, {"VIAJE_IMAGE_STORAGE_DIR": "C:/private", "IMAGE_TOKEN_SECRET": SECRET, "TRIP_IMAGE_CLEANUP_TIME": "03:15"}, clear=False):
            task.start()
        calls = [c for c in fake.add_job.call_args_list if c.kwargs.get("id") == "trip_image_cleanup"]
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].kwargs["replace_existing"])
        self.assertEqual(calls[0].kwargs["max_instances"], 1)
        self.assertTrue(calls[0].kwargs["coalesce"])

    def test_wrapper_closes_session_on_success_and_error_and_missing_config_noops(self):
        import scheduler
        task = scheduler.TaskScheduler(scheduler=Mock())
        session = Mock()
        with patch.dict(os.environ, {"VIAJE_IMAGE_STORAGE_DIR": str(Path(tempfile.gettempdir()).resolve()), "IMAGE_TOKEN_SECRET": SECRET}), patch("database.SessionLocal", return_value=session), patch("trip_image_cleanup.cleanup_trip_images", side_effect=RuntimeError("private")):
            task.cleanup_trip_images_job()
        session.close.assert_called_once()
        with patch.dict(os.environ, {}, clear=True), patch("database.SessionLocal") as factory:
            task.cleanup_trip_images_job()
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
