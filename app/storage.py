"""Stage 3: safe local storage of screenshot files.

Safety rules in this file:
- The type of an image comes from its CONTENT (checked with Pillow), never
  from the filename the user uploaded.
- Stored filenames are generated here (random, like 3f2a...e1.png). A
  user-supplied filename is never used as a file path; it is only kept as
  display text in the database.
- Every file path is checked before it is used: the name must look like one
  we generated, and the final path must sit directly inside the screenshot
  folder. That blocks path traversal such as "../../secret.png".
- Saving never overwrites an existing file.

No screenshot content is logged or printed.
"""

import hashlib
import io
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from app import config


class StorageError(Exception):
    """A file could not be stored, read or removed. The message is safe to show."""


class InvalidImageError(StorageError):
    """The uploaded bytes are not a usable, supported image."""


class UnsafePathError(StorageError):
    """A stored filename was rejected because it could point outside the storage folder."""


@dataclass
class ImageInfo:
    """What we learned by looking inside the image bytes."""

    extension: str  # with a dot, for example ".png"
    mime_type: str  # for example "image/png"


# Pillow's format name -> (extension, MIME type). Only these are accepted.
_FORMATS = {
    "PNG": (".png", "image/png"),
    "JPEG": (".jpg", "image/jpeg"),
    "WEBP": (".webp", "image/webp"),
}

# The only filenames we ever create: 32 hex characters plus a known extension.
_STORED_NAME_PATTERN = re.compile(r"^[0-9a-f]{32}\.(png|jpg|webp)$")


def _storage_dir(storage_dir: str | Path | None) -> Path:
    """Use the folder we were given, or the one from config.py (read at call time)."""
    return Path(storage_dir) if storage_dir else Path(config.SCREENSHOT_DIR)


# ----- Hashing and validation -----
def hash_bytes(data: bytes) -> str:
    """SHA-256 of the original file bytes, as 64 hex characters.

    The same bytes always give the same hash, whatever the filename is.
    """
    return hashlib.sha256(data).hexdigest()


def validate_image_bytes(data: bytes) -> ImageInfo:
    """Check size and content of an upload. Raises InvalidImageError if it is not acceptable."""
    if not data:
        raise InvalidImageError("This file is empty.")
    size_in_mb = len(data) / (1024 * 1024)
    if size_in_mb > config.MAX_FILE_SIZE_MB:
        raise InvalidImageError(
            f"This file is {size_in_mb:.1f} MB. The limit is {config.MAX_FILE_SIZE_MB} MB."
        )
    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = image.format
            if image.width * image.height > config.MAX_IMAGE_PIXELS:
                raise InvalidImageError(
                    f"This image has too many pixels. The limit is {config.MAX_IMAGE_PIXELS:,}."
                )
            image.verify()  # catches corrupted or fake image files
    except InvalidImageError:
        raise
    except Exception as error:  # Pillow can raise several error types for broken files
        raise InvalidImageError("This file could not be read as an image. It may be corrupted.") from error
    if image_format not in _FORMATS:
        raise InvalidImageError("Only PNG, JPG, JPEG and WEBP images are supported.")
    extension, mime_type = _FORMATS[image_format]
    return ImageInfo(extension=extension, mime_type=mime_type)


# ----- Filenames and paths -----
def generate_stored_filename(extension: str) -> str:
    """Make a random, safe filename such as '3f2a...e1.png'."""
    extension = extension.lower()
    if extension not in (".png", ".jpg", ".webp"):
        raise StorageError("Unsupported file extension.")
    return f"{uuid.uuid4().hex}{extension}"


def resolve_stored_path(stored_filename: str, storage_dir: str | Path | None = None) -> Path:
    """Turn a stored filename into a full path, but only if it is safe.

    Raises UnsafePathError for anything that is not a name we generated or
    that would end up outside the storage folder (including through symlinks).
    """
    if not isinstance(stored_filename, str) or not _STORED_NAME_PATTERN.fullmatch(stored_filename):
        raise UnsafePathError("The stored filename is not valid.")
    base_dir = _storage_dir(storage_dir).resolve()
    path = (base_dir / stored_filename).resolve()
    if path.parent != base_dir:
        raise UnsafePathError("The file is not inside the screenshot storage folder.")
    return path


# ----- Saving, reading, deleting -----
def save_image_bytes(data: bytes, stored_filename: str, storage_dir: str | Path | None = None) -> Path:
    """Write the original bytes to the storage folder. Never overwrites an existing file."""
    path = resolve_stored_path(stored_filename, storage_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise StorageError("The screenshot folder could not be created.") from error
    try:
        with open(path, "xb") as file:  # "x" = create new, fail if it already exists
            file.write(data)
    except FileExistsError as error:
        # Not ours to delete: it was there before this save.
        raise StorageError("A file with this name already exists.") from error
    except OSError as error:
        _remove_quietly(path)  # remove the partly written file we just created
        raise StorageError("The screenshot could not be saved to disk.") from error
    return path


def read_stored_file(stored_filename: str, storage_dir: str | Path | None = None) -> bytes | None:
    """Return the file's bytes, or None if it is missing, unsafe or unreadable."""
    try:
        path = resolve_stored_path(stored_filename, storage_dir)
        return path.read_bytes() if path.is_file() else None
    except (StorageError, OSError):
        return None


def delete_stored_file(stored_filename: str, storage_dir: str | Path | None = None) -> bool:
    """Delete one managed file.

    Returns True if a file was removed and False if it was already missing.
    Raises UnsafePathError for unsafe names and StorageError if removal fails.
    """
    path = resolve_stored_path(stored_filename, storage_dir)
    if not path.is_file():
        return False
    try:
        path.unlink()
    except OSError as error:
        raise StorageError("The image file could not be removed.") from error
    return True


def _remove_quietly(path: Path) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
