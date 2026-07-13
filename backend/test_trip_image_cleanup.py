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
