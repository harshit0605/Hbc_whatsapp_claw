"""S3-compatible media storage (MinIO locally, R2/S3 in prod)."""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

import boto3
from botocore.client import Config

from .settings import get_settings


def _client():
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.s3_access_key_id,
        aws_secret_access_key=s.s3_secret_access_key,
        region_name=s.s3_region,
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket() -> None:
    """Create the bucket if it doesn't exist. Safe to call on every startup."""
    s = get_settings()
    c = _client()
    try:
        c.head_bucket(Bucket=s.s3_bucket)
    except Exception:
        c.create_bucket(Bucket=s.s3_bucket)


def put_bytes(data: bytes, *, kind: str, mime: str | None = None) -> str:
    """Upload bytes and return the storage key."""
    s = get_settings()
    today = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    key = f"{kind}/{today}/{uuid.uuid4().hex}"
    if mime:
        ext = _ext_for_mime(mime)
        if ext:
            key += f".{ext}"
    _client().put_object(
        Bucket=s.s3_bucket,
        Key=key,
        Body=io.BytesIO(data),
        ContentType=mime or "application/octet-stream",
    )
    return key


def presigned_get(key: str, ttl: int | None = None) -> str:
    s = get_settings()
    ttl = ttl or s.skills_media_url_ttl_seconds
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": s.s3_bucket, "Key": key},
        ExpiresIn=ttl,
    )


def _ext_for_mime(mime: str) -> str | None:
    return {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "audio/ogg": "ogg",
        "audio/mpeg": "mp3",
        "audio/wav": "wav",
        "video/mp4": "mp4",
        "application/pdf": "pdf",
    }.get(mime)
