import base64
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backend.image_storage import (
    ImageStorage,
    ImageStorageConfigError,
    ImageStoragePathError,
    ImageTokenError,
    ImageValidationError,
)


JPEG = b"\xff\xd8\xff" + b"jpeg-data"
PNG = b"\x89PNG\r\n\x1a\n" + b"png-data"
WEBP = b"RIFF\x08\x00\x00\x00WEBP" + b"webp-data"
SECRET = "s" * 32
NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


class ImageStorageTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        self.storage = ImageStorage(
            root=self.root,
            token_secret=SECRET,
            max_bytes=1024,
            temporary_ttl=timedelta(hours=24),
            now=lambda: NOW,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_recognizes_supported_types_by_magic_bytes_and_ignores_extension(self):
        cases = ((JPEG, "image/jpeg", ".jpg"), (PNG, "image/png", ".png"), (WEBP, "image/webp", ".webp"))
        for data, mime, extension in cases:
            with self.subTest(mime=mime):
                saved = self.storage.save_temp(data, "misleading.exe", mime)
                self.assertEqual(saved.detected_mime, mime)
                self.assertTrue(saved.relative_path.endswith(extension))

    def test_rejects_declared_mime_mismatch_and_unsupported_signature(self):
        with self.assertRaises(ImageValidationError):
            self.storage.save_temp(PNG, "x.png", "image/jpeg")
        with self.assertRaises(ImageValidationError):
            self.storage.save_temp(b"GIF89a", "x.gif", "image/gif")

    def test_rejects_empty_and_oversized_data(self):
        with self.assertRaises(ImageValidationError):
            self.storage.save_temp(b"", "x.jpg", "image/jpeg")
        with self.assertRaises(ImageValidationError):
            self.storage.save_temp(JPEG + b"x" * 1024, "x.jpg", "image/jpeg")

    def test_uses_uuid_path_and_sanitizes_original_name_for_display_only(self):
        saved = self.storage.save_temp(JPEG, "../carpeta\\ foto\x00.jpg ", "image/jpeg")
        path = Path(saved.relative_path)
        self.assertEqual(path.parts[0], "tmp")
        self.assertRegex(path.name, r"^[0-9a-f]{32}\.jpg$")
        self.assertNotIn("carpeta", saved.relative_path)
        self.assertNotIn("/", saved.original_name)
        self.assertNotIn("\\", saved.original_name)
        self.assertNotIn("\x00", saved.original_name)

    def test_save_is_exclusive_and_does_not_overwrite_uuid_collision(self):
        with patch("backend.image_storage.uuid.uuid4") as uuid4:
            uuid4.return_value.hex = "a" * 32
            self.storage.save_temp(JPEG, "one.jpg", "image/jpeg")
            with self.assertRaises(ImageStoragePathError):
                self.storage.save_temp(JPEG + b"second", "two.jpg", "image/jpeg")
        self.assertEqual((self.root / "tmp/20260713" / (("a" * 32) + ".jpg")).read_bytes(), JPEG)

    def test_token_is_opaque_signed_and_contains_no_absolute_path(self):
        saved = self.storage.save_temp(PNG, "x.png", "image/png")
        self.assertNotIn(str(self.root), saved.token)
        self.assertNotIn(SECRET, saved.token)
        ref = self.storage.resolve_temp(saved.token)
        self.assertEqual(ref.relative_path, saved.relative_path)
        self.assertEqual(ref.sha256, saved.sha256)

    def test_rejects_malformed_modified_wrong_version_and_expired_tokens(self):
        saved = self.storage.save_temp(JPEG, "x.jpg", "image/jpeg")
        for token in ("not-a-token", saved.token[:-1] + ("A" if saved.token[-1] != "A" else "B")):
            with self.subTest(token=token):
                with self.assertRaises(ImageTokenError):
                    self.storage.resolve_temp(token)
        payload_part, signature = saved.token.split(".")
        payload = json.loads(base64.urlsafe_b64decode(payload_part + "=="))
        payload["v"] = 99
        wrong_version = self.storage._sign_payload(payload)
        with self.assertRaises(ImageTokenError):
            self.storage.resolve_temp(wrong_version)
        expired_storage = ImageStorage(root=self.root, token_secret=SECRET, now=lambda: NOW + timedelta(days=2))
        with self.assertRaises(ImageTokenError):
            expired_storage.resolve_temp(saved.token)

    def test_resolve_temp_detects_missing_or_modified_file(self):
        saved = self.storage.save_temp(PNG, "x.png", "image/png")
        (self.root / saved.relative_path).write_bytes(PNG + b"tampered")
        with self.assertRaises(ImageValidationError):
            self.storage.resolve_temp(saved.token)

    def test_promote_is_atomic_idempotent_and_returns_sixty_day_expiry(self):
        saved = self.storage.save_temp(WEBP, "x.webp", "image/webp")
        confirmed_at = NOW + timedelta(hours=1)
        first = self.storage.promote(saved.token, confirmed_at)
        second = self.storage.promote(saved.token, confirmed_at)
        self.assertEqual(first, second)
        self.assertEqual(first.expires_at, confirmed_at + timedelta(days=60))
        self.assertEqual(Path(first.relative_path).parts[:2], ("confirmed", "2026"))
        self.assertEqual((self.root / first.relative_path).read_bytes(), WEBP)
        self.assertFalse((self.root / saved.relative_path).exists())
        self.assertEqual(len(list((self.root / "confirmed").rglob("*.webp"))), 1)

    def test_confirmed_resolution_and_delete_are_contained_and_idempotent(self):
        confirmed = self.storage.promote(self.storage.save_temp(JPEG, "x.jpg", "image/jpeg").token, NOW)
        self.assertEqual(self.storage.resolve_confirmed(confirmed.relative_path), (self.root / confirmed.relative_path).resolve())
        self.storage.delete_confirmed(confirmed.relative_path)
        self.storage.delete_confirmed(confirmed.relative_path)
        self.assertFalse((self.root / confirmed.relative_path).exists())

    def test_rejects_traversal_absolute_and_mixed_separator_paths(self):
        for path in ("../outside.jpg", str((self.root.parent / "outside.jpg").resolve()), "confirmed\\..\\outside.jpg", "confirmed/../../outside.jpg"):
            with self.subTest(path=path):
                with self.assertRaises(ImageStoragePathError):
                    self.storage.resolve_confirmed(path)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_rejects_symlink_escape(self):
        outside_dir = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(outside_dir, ignore_errors=True))
        (outside_dir / "image.jpg").write_bytes(JPEG)
        link = self.root / "confirmed" / "link"
        link.parent.mkdir(parents=True)
        try:
            os.symlink(outside_dir, link, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink privilege unavailable: {exc}")
        with self.assertRaises(ImageStoragePathError):
            self.storage.resolve_confirmed("confirmed/link/image.jpg")

    def test_cleanup_removes_only_expired_temps_and_receipts(self):
        old = self.storage.save_temp(JPEG, "old.jpg", "image/jpeg")
        later_storage = ImageStorage(root=self.root, token_secret=SECRET, now=lambda: NOW + timedelta(hours=25))
        fresh = later_storage.save_temp(PNG, "fresh.png", "image/png")
        count = later_storage.cleanup_expired_temps(NOW + timedelta(hours=25))
        self.assertEqual(count, 1)
        self.assertFalse((self.root / old.relative_path).exists())
        self.assertTrue((self.root / fresh.relative_path).exists())


class ImageStorageConfigurationTests(unittest.TestCase):
    def test_reads_environment_and_applies_defaults(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VIAJE_IMAGE_STORAGE_DIR": str(Path(directory).resolve()),
            "VIAJE_IMAGE_MAX_BYTES": "1234",
            "IMAGE_TOKEN_SECRET": SECRET,
        }, clear=True):
            storage = ImageStorage()
            self.assertEqual(storage.max_bytes, 1234)
            self.assertEqual(storage.temporary_ttl, timedelta(hours=24))

    def test_reads_temporary_ttl_hours_from_environment(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VIAJE_IMAGE_STORAGE_DIR": str(Path(directory).resolve()),
            "IMAGE_TOKEN_SECRET": SECRET,
            "VIAJE_IMAGE_TEMP_TTL_HOURS": "6",
        }, clear=True):
            self.assertEqual(ImageStorage().temporary_ttl, timedelta(hours=6))

    def test_rejects_missing_relative_root_nonpositive_limit_and_weak_secret(self):
        invalid_kwargs = (
            {"root": "", "token_secret": SECRET},
            {"root": "relative", "token_secret": SECRET},
            {"root": Path(tempfile.gettempdir()).resolve(), "token_secret": SECRET, "max_bytes": 0},
            {"root": Path(tempfile.gettempdir()).resolve(), "token_secret": "short"},
        )
        for kwargs in invalid_kwargs:
            with self.subTest(kwargs={k: "***" if k == "token_secret" else v for k, v in kwargs.items()}):
                with self.assertRaises(ImageStorageConfigError) as error:
                    ImageStorage(**kwargs)
                self.assertNotIn(kwargs.get("token_secret", "not-present"), str(error.exception))

    def test_requires_timezone_aware_utc_time(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ImageStorageConfigError):
                ImageStorage(root=Path(directory).resolve(), token_secret=SECRET, now=lambda: datetime(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
