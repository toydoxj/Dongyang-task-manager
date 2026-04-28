"""S3 호환 외부 storage 클라이언트.

- 날인요청 첨부 파일을 S3에 보관 (노션 file_upload 의존 X)
- presigned GET URL 발급
- 권한 체크는 호출자(라우터)에서. 본 모듈은 storage I/O만.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any
from uuid import uuid4

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.settings import get_settings

logger = logging.getLogger("storage")


class StorageError(RuntimeError):
    pass


def _build_client():
    s = get_settings()
    if not s.storage_bucket or not s.storage_access_key or not s.storage_secret_key:
        raise StorageError(
            "STORAGE_BUCKET / STORAGE_ACCESS_KEY / STORAGE_SECRET_KEY 미설정"
        )
    kwargs: dict[str, Any] = {
        "region_name": s.storage_region,
        "aws_access_key_id": s.storage_access_key,
        "aws_secret_access_key": s.storage_secret_key,
        "config": Config(signature_version="s3v4"),
    }
    if s.storage_endpoint:
        kwargs["endpoint_url"] = s.storage_endpoint
    return boto3.client("s3", **kwargs)


@lru_cache(maxsize=1)
def get_client():
    return _build_client()


def safe_filename(name: str) -> str:
    """경로 분리·공백 제거. ASCII 외 문자는 그대로 두되 슬래시만 제거."""
    return name.replace("/", "_").replace("\\", "_").strip() or "file.bin"


def build_key(prefix: str, filename: str) -> str:
    """충돌 방지 위해 uuid prefix 부여."""
    return f"{prefix.rstrip('/')}/{uuid4().hex[:8]}_{safe_filename(filename)}"


def put_object(*, key: str, data: bytes, content_type: str) -> None:
    s = get_settings()
    client = get_client()
    try:
        client.put_object(
            Bucket=s.storage_bucket,
            Key=key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )
    except (BotoCoreError, ClientError) as exc:
        logger.exception("S3 put_object 실패: %s", key)
        raise StorageError(f"파일 업로드 실패: {exc}") from exc


def presigned_get_url(*, key: str, filename: str, expires: int = 3600) -> str:
    """다운로드용 presigned URL — Content-Disposition도 함께 부여."""
    s = get_settings()
    client = get_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": s.storage_bucket,
                "Key": key,
                "ResponseContentDisposition": (
                    f'attachment; filename="{safe_filename(filename)}"'
                ),
            },
            ExpiresIn=expires,
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageError(f"presign 실패: {exc}") from exc


def presigned_inline_url(*, key: str, filename: str, expires: int = 3600) -> str:
    """미리보기용 presigned URL — Content-Disposition: inline."""
    s = get_settings()
    client = get_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": s.storage_bucket,
                "Key": key,
                "ResponseContentDisposition": (
                    f'inline; filename="{safe_filename(filename)}"'
                ),
            },
            ExpiresIn=expires,
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageError(f"presign 실패: {exc}") from exc


def delete_object(*, key: str) -> None:
    s = get_settings()
    client = get_client()
    try:
        client.delete_object(Bucket=s.storage_bucket, Key=key)
    except (BotoCoreError, ClientError) as exc:
        logger.warning("S3 delete_object 실패(무시): %s — %s", key, exc)
