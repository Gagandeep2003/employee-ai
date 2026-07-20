"""File storage: S3-compatible object storage (AWS S3, Cloudflare R2, Backblaze B2,
MinIO, ...) when configured, otherwise local disk. No third-party storage proxy.

Cloudflare R2 is the recommended lowest-cost option: 10GB storage and unlimited
egress free, S3-compatible, so this same boto3 client works unmodified -- just
point S3_ENDPOINT_URL at your R2 account endpoint.
"""
import io
import logging
from pathlib import Path
from typing import Tuple

import config

logger = logging.getLogger("ai-employee.storage")

_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client(
            "s3",
            endpoint_url=config.S3_ENDPOINT_URL,
            aws_access_key_id=config.S3_ACCESS_KEY_ID,
            aws_secret_access_key=config.S3_SECRET_ACCESS_KEY,
            region_name=config.S3_REGION,
        )
    return _s3_client


def init_storage() -> str:
    """Ensures the local fallback directory exists. Kept as a callable (rather than
    module-level side effect) so server.py can surface failures at startup."""
    if not config.USE_S3_STORAGE:
        Path(config.STORAGE_LOCAL_DIR).mkdir(parents=True, exist_ok=True)
    return "s3" if config.USE_S3_STORAGE else "local"


def put_object(path: str, data: bytes, content_type: str) -> dict:
    if config.USE_S3_STORAGE:
        client = _get_s3_client()
        client.put_object(Bucket=config.S3_BUCKET, Key=path, Body=data, ContentType=content_type)
        return {"path": path, "size": len(data), "backend": "s3"}

    local_path = Path(config.STORAGE_LOCAL_DIR) / path
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(data)
    return {"path": path, "size": len(data), "backend": "local"}


def get_object(path: str) -> Tuple[bytes, str]:
    if config.USE_S3_STORAGE:
        client = _get_s3_client()
        obj = client.get_object(Bucket=config.S3_BUCKET, Key=path)
        return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")

    local_path = Path(config.STORAGE_LOCAL_DIR) / path
    if not local_path.exists():
        raise FileNotFoundError(path)
    return local_path.read_bytes(), "application/octet-stream"


def delete_object(path: str) -> None:
    if config.USE_S3_STORAGE:
        client = _get_s3_client()
        client.delete_object(Bucket=config.S3_BUCKET, Key=path)
        return
    local_path = Path(config.STORAGE_LOCAL_DIR) / path
    local_path.unlink(missing_ok=True)


APP_NAME = config.APP_NAME
