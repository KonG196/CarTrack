"""On-disk storage for log photos.

Shared by the upload endpoint and the Telegram bot so both write files the
same way: ``<UPLOADS_DIR>/<user_id>/<uuid4><ext>``.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from app.config import settings

# Fallback extensions for image content types when the source has no usable
# filename suffix (Telegram photos never do).
CONTENT_TYPE_EXTENSIONS: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/gif": ".gif",
}


def photo_path(user_id: int, filename: str) -> Path:
    return Path(settings.UPLOADS_DIR) / str(user_id) / filename


def pick_extension(original_name: Optional[str], content_type: Optional[str]) -> str:
    suffix = Path(original_name or "").suffix.lower()
    if suffix and len(suffix) <= 10 and suffix[1:].isalnum():
        return suffix
    return CONTENT_TYPE_EXTENSIONS.get(content_type or "", ".img")


def new_photo_filename(
    original_name: Optional[str] = None, content_type: Optional[str] = None
) -> str:
    """Reserve an on-disk name for an image without writing anything yet.

    Split out of save_photo_file so a caller can name the file inside its
    transaction and write it only once that transaction lands.
    """
    return f"{uuid.uuid4()}{pick_extension(original_name, content_type)}"


def write_photo_file(user_id: int, filename: str, image_bytes: bytes) -> Path:
    path = photo_path(user_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_bytes)
    return path


def delete_photo_file(user_id: int, filename: str) -> None:
    photo_path(user_id, filename).unlink(missing_ok=True)


def save_photo_file(
    user_id: int,
    image_bytes: bytes,
    original_name: Optional[str] = None,
    content_type: Optional[str] = None,
) -> str:
    filename = new_photo_filename(original_name, content_type)
    write_photo_file(user_id, filename, image_bytes)
    return filename
