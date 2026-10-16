"""
Envelope encryption for documents (ADR-04-2 §2.1).

    content   AES-256-GCM with a random 256-bit data key per document; the
              document id is the associated data, so a blob can't be swapped
              onto another document's row
    data key  wrapped (AES-256-GCM) by the key-encryption key (KEK); only the
              wrapped key and the KEK's id are stored
    KEK       DOCUMENT_KEK (base64, 32 bytes) with DOCUMENT_KEK_ID. Not derived
              from SECRET_KEY, so rotating the JWT secret can't lose documents.

Destroying a document destroys its wrapped data key (crypto-shredding): the
ciphertext, in storage or in any backup, can no longer be decrypted.
"""
import base64
import binascii
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import current_app

from app.utils.http import ApiError

NONCE_BYTES = 12
KEY_BYTES = 32


class StorageNotConfigured(ApiError):
    status_code = 503


class IntegrityFailure(Exception):
    """Ciphertext, key or associated data don't match: tampered or wrong key."""


@dataclass(frozen=True)
class Kek:
    key_id: str
    key: bytes


def current_kek() -> Kek:
    raw = current_app.config.get("DOCUMENT_KEK")
    if not raw:
        raise StorageNotConfigured("Document storage is not configured (DOCUMENT_KEK is not set).")
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise StorageNotConfigured("DOCUMENT_KEK must be base64.")
    if len(key) != KEY_BYTES:
        raise StorageNotConfigured("DOCUMENT_KEK must be 32 bytes (base64 of 32 random bytes).")
    return Kek(current_app.config.get("DOCUMENT_KEK_ID") or "env-1", key)


def kek_for(key_id: str) -> Kek:
    kek = current_kek()
    if kek.key_id != key_id:
        raise IntegrityFailure(f"Key {key_id} is not available (current key is {kek.key_id}).")
    return kek


@dataclass(frozen=True)
class Sealed:
    ciphertext: bytes
    nonce: bytes
    wrapped_key: bytes
    key_id: str


def seal(plaintext: bytes, associated: bytes, kek: Kek) -> Sealed:
    data_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(data_key).encrypt(nonce, plaintext, associated)
    wrap_nonce = os.urandom(NONCE_BYTES)
    wrapped = wrap_nonce + AESGCM(kek.key).encrypt(wrap_nonce, data_key, b"document-data-key:" + associated)
    return Sealed(ciphertext, nonce, wrapped, kek.key_id)


def unwrap(wrapped_key: bytes, associated: bytes, kek: Kek) -> bytes:
    try:
        return AESGCM(kek.key).decrypt(wrapped_key[:NONCE_BYTES], wrapped_key[NONCE_BYTES:],
                                       b"document-data-key:" + associated)
    except InvalidTag:
        raise IntegrityFailure("The document key doesn't match this document.")


def open_sealed(ciphertext: bytes, nonce: bytes, data_key: bytes, associated: bytes) -> bytes:
    try:
        return AESGCM(data_key).decrypt(nonce, ciphertext, associated)
    except InvalidTag:
        raise IntegrityFailure("The stored document failed its integrity check.")
