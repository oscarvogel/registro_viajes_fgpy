"""Secure local storage for temporary and confirmed trip images."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Callable


class ImageStorageError(Exception):
    """Base class for storage domain failures."""


class ImageStorageConfigError(ImageStorageError):
    """Storage configuration is invalid."""


class ImageValidationError(ImageStorageError):
    """Image bytes or metadata fail validation."""


class ImageTokenError(ImageStorageError):
    """An image token is invalid or expired."""


class ImageStoragePathError(ImageStorageError):
    """A path is unsafe or cannot be used."""


@dataclass(frozen=True)
class TempImage:
    token: str
    relative_path: str
    detected_mime: str
    sha256: str
    original_name: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class TempImageRef:
    relative_path: str
    path: Path
    detected_mime: str
    sha256: str
    expires_at: datetime


@dataclass(frozen=True)
class ConfirmedImage:
    relative_path: str
    sha256: str
    detected_mime: str
    confirmed_at: datetime
    expires_at: datetime


_MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_UUID_NAME = re.compile(r"^[0-9a-f]{32}\.(?:jpg|png|webp)$")


class ImageStorage:
    DEFAULT_MAX_BYTES = 10 * 1024 * 1024
    DEFAULT_TEMPORARY_TTL = timedelta(hours=24)
    TOKEN_VERSION = 1

    def __init__(
        self,
        root: str | Path | None = None,
        token_secret: str | bytes | None = None,
        max_bytes: int | None = None,
        temporary_ttl: timedelta | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        raw_root = root if root is not None else os.getenv("VIAJE_IMAGE_STORAGE_DIR")
        if raw_root is None or not str(raw_root).strip():
            raise ImageStorageConfigError("Image storage root is required")
        supplied_root = Path(raw_root).expanduser()
        if not supplied_root.is_absolute():
            raise ImageStorageConfigError("Image storage root must be absolute")
        self.root = supplied_root.resolve()

        raw_limit = max_bytes if max_bytes is not None else os.getenv("VIAJE_IMAGE_MAX_BYTES", str(self.DEFAULT_MAX_BYTES))
        try:
            self.max_bytes = int(raw_limit)
        except (TypeError, ValueError) as exc:
            raise ImageStorageConfigError("Image byte limit must be an integer") from exc
        if self.max_bytes <= 0:
            raise ImageStorageConfigError("Image byte limit must be positive")

        raw_secret = token_secret if token_secret is not None else os.getenv("IMAGE_TOKEN_SECRET")
        if isinstance(raw_secret, str):
            secret = raw_secret.encode("utf-8")
        elif isinstance(raw_secret, bytes):
            secret = raw_secret
        else:
            secret = b""
        if len(secret) < 32:
            raise ImageStorageConfigError("Image token secret must contain at least 32 bytes")
        self._secret = secret

        if temporary_ttl is not None:
            self.temporary_ttl = temporary_ttl
        else:
            raw_ttl_hours = os.getenv("VIAJE_IMAGE_TEMP_TTL_HOURS")
            try:
                self.temporary_ttl = (
                    timedelta(hours=float(raw_ttl_hours))
                    if raw_ttl_hours is not None
                    else self.DEFAULT_TEMPORARY_TTL
                )
            except (TypeError, ValueError, OverflowError) as exc:
                raise ImageStorageConfigError("Temporary image TTL hours must be numeric") from exc
        if not isinstance(self.temporary_ttl, timedelta) or self.temporary_ttl <= timedelta(0):
            raise ImageStorageConfigError("Temporary image TTL must be positive")
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._require_utc(self._now(), "Current time")
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _require_utc(value: datetime, label: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ImageStorageConfigError(f"{label} must be timezone-aware UTC")
        return value

    @staticmethod
    def _detect_mime(data: bytes) -> str:
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        raise ImageValidationError("Unsupported or invalid image signature")

    @staticmethod
    def _sanitize_name(original_name: str) -> str:
        value = str(original_name or "").replace("\x00", "")
        value = value.replace("\\", "/").split("/")[-1].strip()
        value = "".join(char for char in value if char.isprintable())
        return value[:255] or "image"

    def _safe_path(self, relative_path: str, *, required_prefix: str | None = None) -> Path:
        if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
            raise ImageStoragePathError("Unsafe image path")
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
            raise ImageStoragePathError("Unsafe image path")
        if required_prefix and (not pure.parts or pure.parts[0] != required_prefix):
            raise ImageStoragePathError("Image path is outside the allowed area")
        candidate = (self.root / Path(*pure.parts)).resolve(strict=False)
        if os.name == "nt":
            def normalized_windows(value: Path) -> str:
                text = str(value)
                if text.startswith("\\\\?\\UNC\\"):
                    text = "\\\\" + text[8:]
                elif text.startswith("\\\\?\\"):
                    text = text[4:]
                return os.path.normcase(os.path.abspath(text))

            root_text = normalized_windows(self.root)
            candidate_text = normalized_windows(candidate)
            try:
                if os.path.commonpath((root_text, candidate_text)) != root_text:
                    raise ImageStoragePathError("Image path escapes storage")
            except ValueError as exc:
                raise ImageStoragePathError("Image path escapes storage") from exc
            return Path(candidate_text)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ImageStoragePathError("Image path escapes storage") from exc
        return candidate

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _decode(value: str) -> bytes:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Non-canonical base64url")
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        canonical = ImageStorage._encode(decoded)
        if not hmac.compare_digest(value, canonical):
            raise ValueError("Non-canonical base64url")
        return decoded

    def _sign_payload(self, payload: dict) -> str:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.new(self._secret, body, hashlib.sha256).digest()
        return f"{self._encode(body)}.{self._encode(signature)}"

    def _decode_signed(self, signed_value: str) -> dict:
        try:
            if not isinstance(signed_value, str) or signed_value.count(".") != 1:
                raise ValueError("Invalid signed value")
            encoded_body, encoded_signature = signed_value.split(".")
            body = self._decode(encoded_body)
            signature = self._decode(encoded_signature)
            expected = hmac.new(self._secret, body, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("Invalid signature")
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Invalid signed payload")
            canonical_body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
            if not hmac.compare_digest(body, canonical_body):
                raise ValueError("Non-canonical signed payload")
            return payload
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeError) as exc:
            raise ImageTokenError("Invalid signed image data") from exc

    def _verify_token(self, token: str) -> dict:
        try:
            payload = self._decode_signed(token)
            if payload.get("v") != self.TOKEN_VERSION:
                raise ImageTokenError("Unsupported image token version")
            expires_at = datetime.fromtimestamp(payload["exp"], timezone.utc)
            if self._now() >= expires_at:
                raise ImageTokenError("Image token has expired")
            if not isinstance(payload.get("id"), str) or not re.fullmatch(r"[0-9a-f]{32}", payload["id"]):
                raise ImageTokenError("Invalid image token")
            self._safe_path(payload["path"], required_prefix="tmp")
            if not re.fullmatch(r"[0-9a-f]{64}", payload.get("sha256", "")):
                raise ImageTokenError("Invalid image token")
            if payload.get("mime") not in _MIME_EXTENSIONS:
                raise ImageTokenError("Invalid image token")
            if not isinstance(payload.get("name"), str) or payload["name"] != self._sanitize_name(payload["name"]):
                raise ImageTokenError("Invalid image token")
            return payload
        except ImageTokenError:
            raise
        except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError, ImageStoragePathError) as exc:
            raise ImageTokenError("Malformed image token") from exc

    @staticmethod
    def _write_exclusive(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        staging = path.parent / f".{path.name}.{uuid.uuid4().hex}.part"
        try:
            descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise ImageStoragePathError("Unable to reserve an image staging path") from exc
        except OSError as exc:
            raise ImageStoragePathError("Unable to reserve an image path") from exc
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(staging, path)
            except FileExistsError as exc:
                raise ImageStoragePathError("Generated image path already exists") from exc
            except OSError as exc:
                raise ImageStoragePathError("Unable to publish image data") from exc
        except Exception:
            raise
        finally:
            staging.unlink(missing_ok=True)

    @classmethod
    def _write_json_exclusive(cls, path: Path, value: dict) -> None:
        cls._write_exclusive(path, json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))

    def save_temp(self, data: bytes, original_name: str, declared_mime: str) -> TempImage:
        if not isinstance(data, bytes) or not data:
            raise ImageValidationError("Image is empty")
        if len(data) > self.max_bytes:
            raise ImageValidationError("Image exceeds configured byte limit")
        detected_mime = self._detect_mime(data)
        if declared_mime != detected_mime:
            raise ImageValidationError("Declared image type does not match image bytes")
        created_at = self._require_utc(self._now(), "Current time")
        expires_at = created_at + self.temporary_ttl
        upload_id = uuid.uuid4().hex
        filename = upload_id + _MIME_EXTENSIONS[detected_mime]
        relative_path = f"tmp/{created_at:%Y%m%d}/{filename}"
        path = self._safe_path(relative_path, required_prefix="tmp")
        digest = hashlib.sha256(data).hexdigest()
        safe_name = self._sanitize_name(original_name)
        self._write_exclusive(path, data)
        metadata_path = path.with_suffix(path.suffix + ".json")
        metadata = {
            "kind": "temp-metadata", "id": upload_id, "path": relative_path,
            "expires_at": expires_at.isoformat(), "sha256": digest, "mime": detected_mime,
        }
        try:
            self._write_exclusive(metadata_path, self._sign_payload(metadata).encode("ascii"))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        payload = {
            "v": self.TOKEN_VERSION,
            "id": upload_id,
            "path": relative_path,
            "sha256": digest,
            "mime": detected_mime,
            "name": safe_name,
            "exp": int(expires_at.timestamp()),
        }
        return TempImage(
            token=self._sign_payload(payload), relative_path=relative_path,
            detected_mime=detected_mime, sha256=digest,
            original_name=safe_name, created_at=created_at, expires_at=expires_at,
        )

    def resolve_temp(self, token: str) -> TempImageRef:
        payload = self._verify_token(token)
        path = self._safe_path(payload["path"], required_prefix="tmp")
        if not path.is_file():
            raise ImageValidationError("Temporary image is unavailable")
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ImageStoragePathError("Temporary image cannot be read") from exc
        if not hmac.compare_digest(digest, payload["sha256"]):
            raise ImageValidationError("Temporary image integrity check failed")
        return TempImageRef(payload["path"], path, payload["mime"], digest, datetime.fromtimestamp(payload["exp"], timezone.utc))

    def _receipt_path(self, upload_id: str) -> Path:
        return self._safe_path(f"receipts/{upload_id}.json", required_prefix="receipts")

    @contextmanager
    def _promotion_lock(self, upload_id: str):
        lock_path = self._safe_path(f"locks/{upload_id}.lock", required_prefix="locks")
        handle = None
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(lock_path, "a+b")
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                deadline = time.monotonic() + 10
                while True:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise ImageStoragePathError("Image promotion lock is unavailable")
                        time.sleep(0.01)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        except ImageStorageError:
            raise
        except OSError as exc:
            raise ImageStoragePathError("Image promotion lock failed") from exc
        finally:
            if handle is not None:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
                handle.close()

    def _validate_confirmed_file(self, path: Path, sha256: str, mime: str) -> None:
        try:
            if not path.is_file() or path.is_symlink():
                raise ImageValidationError("Confirmed image is unavailable")
            data = path.read_bytes()
            if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), sha256):
                raise ImageValidationError("Confirmed image integrity check failed")
            if self._detect_mime(data) != mime or path.suffix != _MIME_EXTENSIONS[mime]:
                raise ImageValidationError("Confirmed image type check failed")
        except ImageStorageError:
            raise
        except OSError as exc:
            raise ImageStoragePathError("Confirmed image cannot be read") from exc

    def _load_receipt(self, receipt_path: Path, token: str, token_payload: dict) -> ConfirmedImage:
        try:
            receipt = self._decode_signed(receipt_path.read_text(encoding="ascii"))
            expected_keys = {
                "kind", "id", "token_hash", "source_sha256", "relative_path", "detected_mime",
                "original_name", "confirmed_at", "expires_at", "retention_days",
            }
            if set(receipt) != expected_keys or receipt["kind"] != "promotion-receipt":
                raise ImageValidationError("Invalid promotion receipt")
            if receipt["id"] != token_payload["id"]:
                raise ImageValidationError("Invalid promotion receipt")
            token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
            if not hmac.compare_digest(receipt["token_hash"], token_hash):
                raise ImageValidationError("Invalid promotion receipt")
            if not hmac.compare_digest(receipt["source_sha256"], token_payload["sha256"]):
                raise ImageValidationError("Invalid promotion receipt")
            if receipt["detected_mime"] != token_payload["mime"] or receipt["original_name"] != token_payload["name"]:
                raise ImageValidationError("Invalid promotion receipt")
            if not isinstance(receipt["retention_days"], int) or isinstance(receipt["retention_days"], bool) or receipt["retention_days"] <= 0:
                raise ImageValidationError("Invalid promotion receipt")
            confirmed_at = datetime.fromisoformat(receipt["confirmed_at"])
            expires_at = datetime.fromisoformat(receipt["expires_at"])
            self._require_utc(confirmed_at, "Receipt confirmation time")
            self._require_utc(expires_at, "Receipt expiry time")
            if expires_at != confirmed_at + timedelta(days=receipt["retention_days"]):
                raise ImageValidationError("Invalid promotion receipt")
            expected_relative = f"confirmed/{confirmed_at:%Y/%m}/{token_payload['id']}{_MIME_EXTENSIONS[token_payload['mime']]}"
            if receipt["relative_path"] != expected_relative:
                raise ImageValidationError("Invalid promotion receipt")
            path = self._safe_path(expected_relative, required_prefix="confirmed")
            self._validate_confirmed_file(path, token_payload["sha256"], token_payload["mime"])
            return ConfirmedImage(expected_relative, token_payload["sha256"], token_payload["mime"], confirmed_at, expires_at)
        except ImageValidationError:
            raise
        except (ImageStorageError, OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise ImageValidationError("Invalid promotion receipt") from exc

    def promote(self, token: str, confirmed_at: datetime, retention_days: int = 60) -> ConfirmedImage:
        confirmed_at = self._require_utc(confirmed_at, "Confirmation time")
        if not isinstance(retention_days, int) or retention_days <= 0:
            raise ImageValidationError("Retention days must be positive")
        payload = self._verify_token(token)
        receipt_path = self._receipt_path(payload["id"])
        with self._promotion_lock(payload["id"]):
            if receipt_path.is_file():
                return self._load_receipt(receipt_path, token, payload)
            source_ref = self.resolve_temp(token)
            try:
                source_data = source_ref.path.read_bytes()
            except OSError as exc:
                raise ImageStoragePathError("Temporary image cannot be read") from exc
            destination_relative = f"confirmed/{confirmed_at:%Y/%m}/{payload['id']}{_MIME_EXTENSIONS[payload['mime']]}"
            destination = self._safe_path(destination_relative, required_prefix="confirmed")
            try:
                self._write_exclusive(destination, source_data)
            except ImageStoragePathError:
                if not destination.exists():
                    raise
                self._validate_confirmed_file(destination, payload["sha256"], payload["mime"])
            confirmed = ConfirmedImage(destination_relative, payload["sha256"], payload["mime"], confirmed_at, confirmed_at + timedelta(days=retention_days))
            receipt = {
                "kind": "promotion-receipt", "id": payload["id"],
                "token_hash": hashlib.sha256(token.encode("ascii")).hexdigest(),
                "source_sha256": payload["sha256"], "relative_path": destination_relative,
                "detected_mime": payload["mime"], "original_name": payload["name"],
                "confirmed_at": confirmed_at.isoformat(), "expires_at": confirmed.expires_at.isoformat(),
                "retention_days": retention_days,
            }
            try:
                self._write_exclusive(receipt_path, self._sign_payload(receipt).encode("ascii"))
                source_ref.path.unlink(missing_ok=True)
                source_ref.path.with_suffix(source_ref.path.suffix + ".json").unlink(missing_ok=True)
            except ImageStorageError:
                raise
            except OSError as exc:
                raise ImageStoragePathError("Image promotion could not be completed") from exc
            return confirmed

    def resolve_confirmed(self, relative_path: str) -> Path:
        path = self._safe_path(relative_path, required_prefix="confirmed")
        if not path.is_file() or not _UUID_NAME.fullmatch(path.name):
            raise ImageStoragePathError("Confirmed image is unavailable")
        return path

    def delete_confirmed(self, relative_path: str) -> None:
        path = self._safe_path(relative_path, required_prefix="confirmed")
        if not _UUID_NAME.fullmatch(path.name):
            raise ImageStoragePathError("Invalid confirmed image path")
        path.unlink(missing_ok=True)

    def cleanup_expired_temps(self, now: datetime | None = None) -> int:
        current = self._require_utc(now or self._now(), "Cleanup time")
        temporary_root = self._safe_path("tmp", required_prefix="tmp")
        if not temporary_root.exists():
            return 0
        removed = 0
        for metadata_path in temporary_root.rglob("*.json"):
            try:
                if metadata_path.is_symlink():
                    continue
                metadata = self._decode_signed(metadata_path.read_text(encoding="ascii"))
                if set(metadata) != {"kind", "id", "path", "expires_at", "sha256", "mime"}:
                    continue
                if metadata["kind"] != "temp-metadata" or not re.fullmatch(r"[0-9a-f]{32}", metadata["id"]):
                    continue
                if metadata["mime"] not in _MIME_EXTENSIONS or not re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"]):
                    continue
                expires_at = datetime.fromisoformat(metadata["expires_at"])
                if expires_at.tzinfo is None or expires_at.utcoffset() != timedelta(0):
                    continue
                image_path = self._safe_path(metadata["path"], required_prefix="tmp")
                if image_path.with_suffix(image_path.suffix + ".json") != metadata_path.resolve():
                    continue
                if expires_at <= current and image_path.parent.resolve().is_relative_to(temporary_root.resolve()):
                    if image_path.is_file() and not image_path.is_symlink():
                        image_path.unlink()
                        removed += 1
                    metadata_path.unlink(missing_ok=True)
            except (ImageStorageError, OSError, ValueError, TypeError, KeyError, UnicodeError):
                continue
        return removed


__all__ = [
    "ConfirmedImage", "ImageStorage", "ImageStorageConfigError", "ImageStorageError",
    "ImageStoragePathError", "ImageTokenError", "ImageValidationError", "TempImage", "TempImageRef",
]
