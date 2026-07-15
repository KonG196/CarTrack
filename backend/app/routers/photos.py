"""Log photo endpoints: upload under a log entry, stream/delete by photo id.

**Storage note.** Files live under ``<UPLOADS_DIR>/<car owner's id>/``, not
under the id of whoever uploaded them. On a shared car those differ, and
keying the directory on the uploader would file an editor's photo where no
one else — the owner included — would look for it.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import ROLE_EDITOR, ROLE_OWNER, ROLE_VIEWER
from app.auth import get_current_user
from app.database import get_db
from app.models import Car, LogEntry, LogPhoto, User
from app.routers.logs import get_owned_log
from app.schemas import PhotoOut
from app.services.photos import photo_path, save_photo_file

router = APIRouter(tags=["photos"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def get_owned_photo(
    db: Session, user: User, photo_id: int, min_role: str = ROLE_OWNER
) -> LogPhoto:
    """Fetch a photo the user may act on at ``min_role``, or raise 404/403.

    ``min_role`` defaults to 'owner' so a caller that forgets to widen it
    fails closed.
    """
    photo = db.execute(select(LogPhoto).where(LogPhoto.id == photo_id)).scalar_one_or_none()
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
    # One access check, on the car the photo hangs under.
    get_owned_log(db, user, photo.log_entry_id, min_role=min_role)
    return photo


def _storage_owner_id(db: Session, photo: LogPhoto) -> int:
    """The user id whose directory holds this photo: the car's owner."""
    return db.execute(
        select(Car.user_id)
        .join(LogEntry, LogEntry.car_id == Car.id)
        .where(LogEntry.id == photo.log_entry_id)
    ).scalar_one()


@router.post(
    "/logs/{log_id}/photos", response_model=PhotoOut, status_code=status.HTTP_201_CREATED
)
async def upload_photo(
    log_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LogPhoto:
    log = get_owned_log(db, current_user, log_id, min_role=ROLE_EDITOR)

    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only image uploads are supported",
        )
    too_large = HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail="Image is too large (max 10 MB)",
    )
    # Same cap strategy as the OCR endpoint: check the spooled size first,
    # then read at most one byte over the limit.
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise too_large
    image_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise too_large

    owner_id = db.execute(select(Car.user_id).where(Car.id == log.car_id)).scalar_one()
    filename = save_photo_file(owner_id, image_bytes, file.filename, file.content_type)
    photo = LogPhoto(
        log_entry_id=log.id,
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        size=len(image_bytes),
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


@router.get("/photos/{photo_id}")
def get_photo(
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    photo = get_owned_photo(db, current_user, photo_id, min_role=ROLE_VIEWER)
    path = photo_path(_storage_owner_id(db, photo), photo.filename)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
    return FileResponse(path, media_type=photo.content_type)


@router.delete("/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    photo = get_owned_photo(db, current_user, photo_id, min_role=ROLE_EDITOR)
    path = photo_path(_storage_owner_id(db, photo), photo.filename)
    db.delete(photo)
    db.commit()
    path.unlink(missing_ok=True)
    return None
