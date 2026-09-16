"""
Image upload helper for post cover images.

Uploaded files are saved under MEDIA_ROOT/posts/ with a random filename
(the original extension is preserved). The API returns a URL path such as
"/media/posts/<uuid>.jpg", which is also served statically by FastAPI's
StaticFiles mount (configured in main.py) so the image is directly
browsable/downloadable by clients.
"""

import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile, status

MEDIA_ROOT = Path("media")
POSTS_MEDIA_DIR = MEDIA_ROOT / "posts"
POSTS_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# Keep this conservative — extend as needed.
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


def save_post_image(upload: Optional[UploadFile]) -> Optional[str]:
    """
    Validate and persist an uploaded image for a post.

    Returns the relative URL path (e.g. "/media/posts/<uuid>.jpg") to store
    on the Post.image column, or None if no file was provided.
    Raises HTTPException(400) on invalid file type / size.
    """
    if upload is None or not upload.filename:
        return None

    if upload.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image type '{upload.content_type}'. "
            f"Allowed types: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}",
        )

    # Read into memory to enforce the size limit, then write to disk.
    # (Fine for a 5 MB cap; for much larger files you'd stream to disk in chunks.)
    contents = upload.file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image too large. Max size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    ext = os.path.splitext(upload.filename)[1].lower() or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    dest_path = POSTS_MEDIA_DIR / filename

    with open(dest_path, "wb") as f:
        f.write(contents)

    # Reset pointer in case the same UploadFile object is read again elsewhere.
    upload.file.seek(0)

    return f"/media/posts/{filename}"


def delete_post_image(image_url: Optional[str]) -> None:
    """Best-effort removal of a post's image file from disk (e.g. on post delete)."""
    if not image_url:
        return
    filename = os.path.basename(image_url)
    path = POSTS_MEDIA_DIR / filename
    try:
        if path.exists():
            path.unlink()
    except OSError:
        # Non-fatal — don't block the API response over a stray file on disk.
        pass