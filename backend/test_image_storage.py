import base64
import json
import os
import tempfile
import concurrent.futures
import time
import stat
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from backend.image_storage import (
    ImageStorage,
    ImageStorageConfigError,
    ImageStoragePathError,
    ImageTokenExpiredError,
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

    def test_describe_token_returns_verified_safe_metadata(self):
        saved = self.storage.save_temp(JPEG, "../ticket.jpg", "image/jpeg")
        described = self.storage.describe_token(saved.token)
        self.assertEqual(described.original_name, "ticket.jpg")
        self.assertEqual(described.sha256, saved.sha256)
        self.assertEqual(described.relative_path, saved.relative_path)

    def test_expired_token_has_explicit_exception_type(self):
        saved = self.storage.save_temp(JPEG, "ticket.jpg", "image/jpeg")
        expired = ImageStorage(self.root, SECRET, max_bytes=1024, now=lambda: NOW + timedelta(days=2))
        with self.assertRaises(ImageTokenExpiredError):
            expired.describe_token(saved.token)

    def test_revert_promotion_restores_temp_and_allows_promotion_again(self):
        saved = self.storage.save_temp(JPEG, "ticket.jpg", "image/jpeg")
        confirmed = self.storage.promote(saved.token, NOW)
        self.storage.revert_promotion(saved.token, confirmed)
        self.assertEqual(self.storage.resolve_temp(saved.token).path.read_bytes(), JPEG)
        self.assertFalse((self.root / confirmed.relative_path).exists())
        promoted_again = self.storage.promote(saved.token, NOW)
        self.assertEqual(promoted_again.relative_path, confirmed.relative_path)

    def test_revert_is_idempotent_and_rejects_wrong_confirmation(self):
        saved = self.storage.save_temp(JPEG, "ticket.jpg", "image/jpeg")
        confirmed = self.storage.promote(saved.token, NOW)
        self.storage.revert_promotion(saved.token, confirmed)
        self.storage.revert_promotion(saved.token, confirmed)
        wrong = SimpleNamespace(**{**confirmed.__dict__, "sha256": "0" * 64})
        with self.assertRaises(ImageValidationError):
            self.storage.revert_promotion(saved.token, wrong)

    def test_revert_does_not_overwrite_invalid_existing_temp(self):
        saved = self.storage.save_temp(JPEG, "ticket.jpg", "image/jpeg")
        confirmed = self.storage.promote(saved.token, NOW)
        temp_path = self.root / saved.relative_path
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_bytes(PNG)
        with self.assertRaises(ImageValidationError):
            self.storage.revert_promotion(saved.token, confirmed)
        self.assertEqual(temp_path.read_bytes(), PNG)
        self.assertTrue((self.root / confirmed.relative_path).exists())

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

    def test_rejects_noncanonical_base64url_token_segments(self):
        saved = self.storage.save_temp(JPEG, "x.jpg", "image/jpeg")
        body, signature = saved.token.split(".")
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        last_index = alphabet.index(signature[-1])
        alternate_signature = signature[:-1] + alphabet[(last_index & 0b110000) | ((last_index + 1) & 0b001111)]
        self.assertEqual(
            base64.urlsafe_b64decode(signature + "="),
            base64.urlsafe_b64decode(alternate_signature + "="),
        )
        variants = (
            f"{body}!.{signature}", f"{body}=.{signature}", f" {body}.{signature}",
            f"{body}.{signature}=", f"{body}.\n{signature}", f".{signature}", f"{body}.",
            f"{body}.{alternate_signature}",
        )
        for token in variants:
            with self.subTest(token=repr(token)):
                with self.assertRaises(ImageTokenError):
                    self.storage.resolve_temp(token)

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

    def test_retention_is_fixed_to_exactly_sixty_days(self):
        for invalid in (True, 1, 61):
            with self.subTest(invalid=invalid):
                saved = self.storage.save_temp(JPEG, "x.jpg", "image/jpeg")
                with self.assertRaises(ImageValidationError):
                    self.storage.promote(saved.token, NOW, retention_days=invalid)

    def test_idempotent_retry_rejects_tampered_signed_receipt(self):
        saved = self.storage.save_temp(JPEG, "safe name.jpg", "image/jpeg")
        self.storage.promote(saved.token, NOW)
        receipt = self.root / "receipts" / f"{Path(saved.relative_path).stem}.json"
        receipt.write_text(receipt.read_text(encoding="utf-8")[:-1] + "A", encoding="utf-8")
        with self.assertRaises(ImageValidationError) as error:
            self.storage.promote(saved.token, NOW)
        self.assertNotIn(str(self.root), str(error.exception))

    def test_idempotent_retry_revalidates_confirmed_file_hash_and_magic(self):
        saved = self.storage.save_temp(PNG, "safe.png", "image/png")
        confirmed = self.storage.promote(saved.token, NOW)
        (self.root / confirmed.relative_path).write_bytes(JPEG)
        with self.assertRaises(ImageValidationError):
            self.storage.promote(saved.token, NOW)

    def test_revalidation_rejects_files_larger_than_configured_limit(self):
        temporary = self.storage.save_temp(JPEG, "temp.jpg", "image/jpeg")
        (self.root / temporary.relative_path).write_bytes(JPEG + b"x" * 2048)
        with self.assertRaises(ImageValidationError):
            self.storage.resolve_temp(temporary.token)
        confirmed_temp = self.storage.save_temp(PNG, "confirmed.png", "image/png")
        confirmed = self.storage.promote(confirmed_temp.token, NOW)
        (self.root / confirmed.relative_path).write_bytes(PNG + b"x" * 2048)
        with self.assertRaises(ImageValidationError):
            self.storage.promote(confirmed_temp.token, NOW)

    def test_streaming_inspection_rejects_size_change_during_read(self):
        saved = self.storage.save_temp(JPEG, "x.jpg", "image/jpeg")
        path = self.root / saved.relative_path
        with patch.object(self.storage, "_assert_no_symlink_components"), patch(
            "backend.image_storage.os.lstat",
            side_effect=(SimpleNamespace(st_size=len(JPEG)), SimpleNamespace(st_size=len(JPEG) + 1)),
        ):
            with self.assertRaises(ImageValidationError):
                self.storage._inspect_file(path, "tmp")

    def test_receipt_retry_removes_crash_left_temp_artifacts(self):
        saved = self.storage.save_temp(JPEG, "safe.jpg", "image/jpeg")
        confirmed = self.storage.promote(saved.token, NOW)
        source = self.root / saved.relative_path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes((self.root / confirmed.relative_path).read_bytes())
        metadata = {
            "kind": "temp-metadata", "id": source.stem, "path": saved.relative_path,
            "expires_at": saved.expires_at.isoformat(), "sha256": saved.sha256, "mime": saved.detected_mime,
        }
        source.with_suffix(source.suffix + ".json").write_text(self.storage._sign_payload(metadata), encoding="ascii")
        self.assertEqual(self.storage.promote(saved.token, NOW), confirmed)
        self.assertFalse(source.exists())
        self.assertFalse(source.with_suffix(source.suffix + ".json").exists())

    def test_committed_promotion_ignores_temp_unlink_failures(self):
        saved = self.storage.save_temp(JPEG, "safe.jpg", "image/jpeg")
        source = self.root / saved.relative_path
        original_unlink = Path.unlink

        def fail_temp_unlink(path, *args, **kwargs):
            if path == source or path == source.with_suffix(source.suffix + ".json"):
                raise PermissionError("injected unlink failure")
            return original_unlink(path, *args, **kwargs)

        with patch("backend.image_storage.Path.unlink", autospec=True, side_effect=fail_temp_unlink):
            first = self.storage.promote(saved.token, NOW)
        second = self.storage.promote(saved.token, NOW)
        self.assertEqual(first, second)

    def test_receipt_retry_ignores_corrupt_or_oversized_temp_residue(self):
        for residue in (b"corrupt", JPEG + b"x" * 2048):
            with self.subTest(size=len(residue)), tempfile.TemporaryDirectory() as directory:
                storage = ImageStorage(root=Path(directory).resolve(), token_secret=SECRET, max_bytes=1024, now=lambda: NOW)
                saved = storage.save_temp(JPEG, "safe.jpg", "image/jpeg")
                confirmed = storage.promote(saved.token, NOW)
                source = storage.root / saved.relative_path
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(residue)
                self.assertEqual(storage.promote(saved.token, NOW), confirmed)
                self.assertTrue(source.exists())

    def test_idempotent_retry_rejects_semantically_tampered_receipt_fields(self):
        fields = {
            "id": "f" * 32,
            "token_hash": "0" * 64,
            "source_sha256": "0" * 64,
            "relative_path": "confirmed/2026/07/" + ("f" * 32) + ".jpg",
            "detected_mime": "image/png",
            "original_name": "other.jpg",
            "confirmed_at": "2026-07-13T12:00:00",
            "expires_at": (NOW + timedelta(days=61)).isoformat(),
            "retention_days": 61,
        }
        for field, value in fields.items():
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as directory:
                    storage = ImageStorage(root=Path(directory).resolve(), token_secret=SECRET, now=lambda: NOW)
                    saved = storage.save_temp(JPEG, "safe.jpg", "image/jpeg")
                    storage.promote(saved.token, NOW)
                    receipt = storage.root / "receipts" / f"{Path(saved.relative_path).stem}.json"
                    payload = storage._decode_signed(receipt.read_text(encoding="ascii"))
                    payload[field] = value
                    receipt.write_text(storage._sign_payload(payload), encoding="ascii")
                    with self.assertRaises(ImageValidationError):
                        storage.promote(saved.token, NOW)

    def test_two_concurrent_promotions_return_same_confirmed_image(self):
        saved = self.storage.save_temp(WEBP, "safe.webp", "image/webp")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.storage.promote, saved.token, NOW) for _ in range(2)]
            results = [future.result(timeout=5) for future in futures]
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(list((self.root / "confirmed").rglob("*.webp"))), 1)
        self.assertEqual(len(list((self.root / "receipts").glob("*.json"))), 1)

    def test_wedged_promotion_lock_times_out_with_domain_error(self):
        storage = ImageStorage(root=self.root, token_secret=SECRET, now=lambda: NOW, lock_timeout_seconds=0.02)
        saved = storage.save_temp(JPEG, "x.jpg", "image/jpeg")
        started = time.monotonic()
        with patch.object(storage, "_try_acquire_lock", return_value=False):
            with self.assertRaises(ImageStoragePathError):
                storage.promote(saved.token, NOW)
        self.assertLess(time.monotonic() - started, 1)

    def test_promote_does_not_overwrite_preexisting_destination_mismatch(self):
        saved = self.storage.save_temp(JPEG, "safe.jpg", "image/jpeg")
        destination = self.root / "confirmed/2026/07" / Path(saved.relative_path).name
        destination.parent.mkdir(parents=True)
        destination.write_bytes(PNG)
        with self.assertRaises(ImageValidationError):
            self.storage.promote(saved.token, NOW)
        self.assertEqual(destination.read_bytes(), PNG)

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

    def test_cleanup_continues_past_malformed_tampered_and_naive_metadata(self):
        expired = self.storage.save_temp(JPEG, "expired.jpg", "image/jpeg")
        malformed = self.storage.save_temp(PNG, "malformed.png", "image/png")
        naive = self.storage.save_temp(WEBP, "naive.webp", "image/webp")
        malformed_meta = (self.root / malformed.relative_path).with_suffix(".png.json")
        malformed_meta.write_text("not-signed-metadata", encoding="ascii")
        naive_meta = (self.root / naive.relative_path).with_suffix(".webp.json")
        payload = self.storage._decode_signed(naive_meta.read_text(encoding="ascii"))
        payload["expires_at"] = "2026-07-13T13:00:00"
        naive_meta.write_text(self.storage._sign_payload(payload), encoding="ascii")
        confirmed = self.storage.promote(self.storage.save_temp(JPEG, "confirmed.jpg", "image/jpeg").token, NOW)
        count = self.storage.cleanup_expired_temps(NOW + timedelta(days=2))
        self.assertEqual(count, 1)
        self.assertFalse((self.root / expired.relative_path).exists())
        self.assertTrue((self.root / malformed.relative_path).exists())
        self.assertTrue((self.root / naive.relative_path).exists())
        self.assertTrue((self.root / confirmed.relative_path).exists())

    def test_cleanup_sweeps_only_aged_unambiguous_orphans_and_parts(self):
        tmp = self.root / "tmp/20260710"
        tmp.mkdir(parents=True)
        old_image = tmp / (("a" * 32) + ".jpg")
        recent_image = tmp / (("b" * 32) + ".png")
        old_part = tmp / ".write.part"
        recent_part = tmp / ".recent.part"
        orphan_meta = tmp / (("c" * 32) + ".webp.json")
        for path, data in ((old_image, JPEG), (recent_image, PNG), (old_part, b"partial"), (recent_part, b"partial"), (orphan_meta, b"invalid")):
            path.write_bytes(data)
        old_timestamp = (NOW - timedelta(days=2)).timestamp()
        for path in (old_image, old_part, orphan_meta):
            os.utime(path, (old_timestamp, old_timestamp))
        self.storage.cleanup_expired_temps(NOW)
        self.assertFalse(old_image.exists())
        self.assertFalse(old_part.exists())
        self.assertFalse(orphan_meta.exists())
        self.assertTrue(recent_image.exists())
        self.assertTrue(recent_part.exists())

    def test_namespace_containment_rejects_cross_namespace_resolution(self):
        with patch.object(self.storage, "_namespace_root", return_value=(self.root / "tmp").resolve()):
            with self.assertRaises(ImageStoragePathError):
                self.storage._safe_path("confirmed/" + ("a" * 32) + ".jpg", required_prefix="confirmed")

    def test_namespace_root_symlink_is_rejected_without_os_privileges(self):
        original_lstat = os.lstat
        for namespace in ("tmp", "confirmed"):
            with self.subTest(namespace=namespace):
                target = self.root / namespace
                target.mkdir(exist_ok=True)

                def fake_lstat(path, *args, **kwargs):
                    result = original_lstat(path, *args, **kwargs)
                    if Path(path) == target:
                        values = list(result)
                        values[0] = stat.S_IFLNK | 0o777
                        return os.stat_result(values)
                    return result

                with patch("backend.image_storage.os.lstat", side_effect=fake_lstat):
                    with self.assertRaises(ImageStoragePathError):
                        self.storage._namespace_root(namespace)

    def test_exclusive_publication_fails_closed_when_hard_links_unavailable(self):
        saved = self.storage.save_temp(JPEG, "x.jpg", "image/jpeg")
        destination = self.root / "confirmed/2026/07" / Path(saved.relative_path).name
        receipt = self.root / "receipts" / f"{Path(saved.relative_path).stem}.json"
        with patch("backend.image_storage.os.link", side_effect=OSError("unsupported")):
            with self.assertRaises(ImageStoragePathError) as error:
                self.storage.promote(saved.token, NOW)
        self.assertNotIn("unsupported", str(error.exception))
        self.assertFalse(destination.exists())
        self.assertFalse(receipt.exists())
        self.assertFalse(list(destination.parent.glob("*.part")) if destination.parent.exists() else [])

    def test_exclusive_staging_write_failure_leaves_no_authoritative_file(self):
        destination = self.root / "confirmed/2026/07" / (("d" * 32) + ".jpg")
        with patch("backend.image_storage.os.fsync", side_effect=OSError("write failed")):
            with self.assertRaises(ImageStoragePathError):
                self.storage._write_exclusive(destination, JPEG)
        self.assertFalse(destination.exists())

    def test_mutating_clock_is_validated_on_every_use(self):
        values = iter((NOW, datetime(2026, 7, 13, 12, 1)))
        storage = ImageStorage(root=self.root, token_secret=SECRET, now=lambda: next(values))
        with self.assertRaises(ImageStorageConfigError):
            storage.save_temp(JPEG, "x.jpg", "image/jpeg")

    def test_mutating_clock_rejects_non_utc_offset(self):
        values = iter((NOW, datetime(2026, 7, 13, 12, 1, tzinfo=timezone(timedelta(hours=-3)))))
        storage = ImageStorage(root=self.root, token_secret=SECRET, now=lambda: next(values))
        with self.assertRaises(ImageStorageConfigError):
            storage.save_temp(JPEG, "x.jpg", "image/jpeg")


class ImageStorageConfigurationTests(unittest.TestCase):
    def test_root_creation_os_error_is_sanitized(self):
        root = Path(tempfile.gettempdir()).resolve() / "private-storage"
        with patch("backend.image_storage.Path.mkdir", side_effect=PermissionError("sensitive path")):
            with self.assertRaises(ImageStorageConfigError) as error:
                ImageStorage(root=root, token_secret=SECRET)
        self.assertNotIn("sensitive path", str(error.exception))
        self.assertNotIn(str(root), str(error.exception))

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
