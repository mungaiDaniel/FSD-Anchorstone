"""
Where encrypted document bytes live. Only ciphertext reaches a store, keyed
documents/yyyy/mm/<uuid> (no names or ID numbers in keys).

    LocalDocumentStore   a folder on disk (development, tests, single server)
    (later)              S3-compatible / Azure Blob, behind the same interface

get_store() picks the backend from DOCUMENT_STORE_BACKEND.
"""
import os
import pathlib
from typing import Protocol

from flask import current_app

from app.Documents.crypto import StorageNotConfigured


class DocumentStore(Protocol):
    name: str

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...


class LocalDocumentStore:
    name = "local"

    def __init__(self, root: str):
        self.root = pathlib.Path(root).resolve()

    def _path(self, key: str) -> pathlib.Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid storage key.")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data)
        os.replace(tmp, path)  # never a half-written blob under the real key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


def get_store() -> DocumentStore:
    backend = (current_app.config.get("DOCUMENT_STORE_BACKEND") or "local").lower()
    if backend == "local":
        root = current_app.config.get("DOCUMENT_STORE_PATH") or os.path.join(current_app.instance_path, "documents")
        return LocalDocumentStore(root)
    raise StorageNotConfigured(f"Unknown DOCUMENT_STORE_BACKEND: {backend}.")
