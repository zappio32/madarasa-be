import io
import mimetypes
from pathlib import Path
import secrets

import boto3
from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import get_settings

ALLOWED_FORMATS = {"JPEG": ("image/jpeg", ".jpg"), "PNG": ("image/png", ".png"), "WEBP": ("image/webp", ".webp")}


async def store_image(upload: UploadFile) -> tuple[str, str, bytes]:
    settings = get_settings()
    raw = await upload.read(settings.max_upload_size_mb * 1024 * 1024 + 1)
    if not raw or len(raw) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be non-empty and within the upload size limit.")
    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        image = Image.open(io.BytesIO(raw))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=415, detail="Upload must be a valid JPEG, PNG, or WebP image.") from exc
    if image.format not in ALLOWED_FORMATS or image.width > 8000 or image.height > 8000:
        raise HTTPException(status_code=415, detail="Unsupported image format or dimensions.")
    mime_type, extension = ALLOWED_FORMATS[image.format]
    image.thumbnail((2400, 2400))
    output = io.BytesIO()
    image.save(output, format=image.format, optimize=True, quality=85)
    content = output.getvalue()
    key = f"{secrets.token_hex(16)}{extension}"
    if settings.media_storage == "s3":
        client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint or None,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            region_name=settings.storage_region,
        )
        client.put_object(Bucket=settings.storage_bucket, Key=key, Body=content, ContentType=mime_type)
    else:
        target = Path(settings.local_media_path).resolve()
        target.mkdir(parents=True, exist_ok=True)
        (target / key).write_bytes(content)
    return key, mime_type, content


def read_image(key: str) -> tuple[bytes, str]:
    settings = get_settings()
    if settings.media_storage == "s3":
        client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint or None,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            region_name=settings.storage_region,
        )
        item = client.get_object(Bucket=settings.storage_bucket, Key=key)
        return item["Body"].read(), item["ContentType"]
    target = (Path(settings.local_media_path).resolve() / key).resolve()
    if target.parent != Path(settings.local_media_path).resolve() or not target.is_file():
        raise FileNotFoundError(key)
    return target.read_bytes(), mimetypes.guess_type(key)[0] or "application/octet-stream"


def delete_image(key: str) -> None:
    settings = get_settings()
    if settings.media_storage == "s3":
        client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint or None,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            region_name=settings.storage_region,
        )
        client.delete_object(Bucket=settings.storage_bucket, Key=key)
    else:
        target = Path(settings.local_media_path).resolve() / key
        if target.is_file():
            target.unlink()

