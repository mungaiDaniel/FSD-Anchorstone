"""
Symmetric encryption for secrets we store in the database (currently: the SMTP
password an admin enters in Settings → Email Sending). Never store these in
plaintext — config.py already has one hardcoded mail password fallback, which
this is explicitly meant not to repeat.

The key is derived from the app's SECRET_KEY rather than a second secret to
manage — anyone who could read SECRET_KEY (needed to forge JWTs anyway) could
already impersonate any user, so this doesn't weaken anything, it just avoids
storing credentials as plain text at rest.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _fernet(app_secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(app_secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(plain_text: str, app_secret: str) -> str:
    if not plain_text:
        return ""
    return _fernet(app_secret).encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str, app_secret: str) -> str:
    if not token:
        return ""
    try:
        return _fernet(app_secret).decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # SECRET_KEY changed since this was encrypted, or the value predates
        # encryption — treat as unusable rather than crashing the caller.
        return ""
