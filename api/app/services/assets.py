"""Storage for instance files: S3/MinIO in deployment, a local directory otherwise.

Instances are pure functions of their seed, so a missing object is never data loss:
the caller regenerates it. That keeps the 30-day expiry of the doc (12.1) harmless.
"""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Protocol

from starlette.concurrency import run_in_threadpool

from app.settings import get_settings


class AssetStore(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...
    async def get(self, key: str) -> bytes | None: ...


class LocalStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    async def put(self, key: str, data: bytes) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, key: str) -> bytes | None:
        path = self.root / key
        return path.read_bytes() if path.exists() else None


class S3Store:
    def __init__(self) -> None:
        import boto3

        settings = get_settings()
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
        self._ready = False

    def _ensure_bucket(self) -> None:
        if self._ready:
            return
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.bucket)
        self._ready = True

    async def put(self, key: str, data: bytes) -> None:
        def _put() -> None:
            self._ensure_bucket()
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data)

        await run_in_threadpool(_put)

    async def get(self, key: str) -> bytes | None:
        def _get() -> bytes | None:
            self._ensure_bucket()
            try:
                obj = self.client.get_object(Bucket=self.bucket, Key=key)
            except Exception:
                return None
            body: bytes = obj["Body"].read()
            return body

        return await run_in_threadpool(_get)


_store: AssetStore | None = None


def store() -> AssetStore:
    global _store
    if _store is None:
        settings = get_settings()
        if settings.s3_endpoint and settings.s3_access_key:
            _store = S3Store()
        else:
            _store = LocalStore(Path("/tmp/bayt-assets") / settings.bayt_env)
    return _store


def set_store(value: AssetStore | None) -> None:
    global _store
    _store = value


def gzip_bytes(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=6, mtime=0)
