# Purpose: provide an application-layer encryption boundary for sensitive persisted fields.
# Responsibilities: define the EncryptionProvider interface, a development NoopEncryptionProvider,
#   and a local Fernet-based provider; record a key version with every ciphertext so keys can be
#   rotated; and expose an always-on cipher for signing secrets that must never be stored in
#   plaintext. Dependencies: cryptography (Fernet), settings.
from __future__ import annotations

import base64
import hashlib
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import Settings, get_settings

# A stored value is "<mode>:<key_version>:<payload>" so decrypt is self-describing and rotatable.
_SEPARATOR = ":"
# Development fallback so signing secrets are still encrypted (never plaintext) without a configured
# key. It is intentionally not secret; production must set EVIDENCE_ENCRYPTION_KEY.
_DEV_KEY_MATERIAL = "deceptiforge-insecure-development-key"


class EncryptionError(Exception):
    """Raised when decryption fails (wrong key, corrupted, or tampered ciphertext)."""


def _fernet_for(secret: str) -> Fernet:
    """Derive a valid Fernet key from an arbitrary passphrase."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _key_version(secret: str) -> str:
    return "k" + hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


class EncryptionProvider(Protocol):
    mode: str
    key_version: str

    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, token: str) -> str: ...


class NoopEncryptionProvider:
    """Stores values reversibly encoded but NOT encrypted. Development/evidence use only."""

    mode = "disabled"
    key_version = "none"

    def encrypt(self, plaintext: str) -> str:
        payload = base64.urlsafe_b64encode(plaintext.encode("utf-8")).decode("ascii")
        return _SEPARATOR.join((self.mode, self.key_version, payload))

    def decrypt(self, token: str) -> str:
        _, _, payload = token.split(_SEPARATOR, 2)
        return base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")


class LocalEncryptionProvider:
    """Fernet (AES-CBC + HMAC) authenticated encryption using an app-managed key."""

    mode = "local"

    def __init__(self, key_material: str) -> None:
        self._fernet = _fernet_for(key_material)
        self.key_version = _key_version(key_material)

    def encrypt(self, plaintext: str) -> str:
        token = self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        return _SEPARATOR.join((self.mode, self.key_version, token))

    def decrypt(self, token: str) -> str:
        try:
            _, _, payload = token.split(_SEPARATOR, 2)
            return self._fernet.decrypt(payload.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as error:
            raise EncryptionError("could not decrypt value") from error


def build_encryption_provider(settings: Settings) -> EncryptionProvider:
    """Return the evidence encryption provider selected by settings."""
    if settings.evidence_encryption_mode == "local":
        if not settings.evidence_encryption_key:
            raise RuntimeError("EVIDENCE_ENCRYPTION_MODE=local requires EVIDENCE_ENCRYPTION_KEY")
        return LocalEncryptionProvider(settings.evidence_encryption_key)
    if settings.evidence_encryption_mode == "disabled":
        return NoopEncryptionProvider()
    raise RuntimeError(f"unsupported EVIDENCE_ENCRYPTION_MODE: {settings.evidence_encryption_mode}")


def secret_cipher(settings: Settings) -> LocalEncryptionProvider:
    """Return an always-encrypting cipher for signing secrets (never plaintext, even in dev)."""
    return LocalEncryptionProvider(settings.evidence_encryption_key or _DEV_KEY_MATERIAL)


def get_encryption_provider() -> EncryptionProvider:
    return build_encryption_provider(get_settings())
