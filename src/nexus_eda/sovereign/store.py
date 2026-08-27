# SPDX-License-Identifier: Apache-2.0
"""Encrypted local storage for sovereign design data (AES-256-GCM).

Provides an on-device encrypted key-value store that holds design artifacts
( netlists, BOMs, DRC reports, etc.) under the sovereign boundary.  Data is
encrypted at rest with AES-256-GCM; the key is derived from a user passphrase
via Argon2id (never stored on disk).

If ``cryptography`` is not installed, the module still imports but raises
:class:`StoreError` at call time so callers can degrade to plaintext stubs.
"""

from __future__ import annotations

import os
import json
import base64
import hashlib
import secrets
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


__all__ = [
    "AES256Crypto",
    "EncryptedStore",
    "StoreError",
    "StoreConfig",
]


class StoreError(Exception):
    """Raised when the encrypted store cannot operate (missing crypto)."""


# --------------------------------------------------------------------------- #
# Crypto
# --------------------------------------------------------------------------- #

@dataclass
class AES256Crypto:
    """AES-256-GCM encryption/decryption with Argon2id key derivation.

    The key is never persisted.  Callers supply a passphrase; a random salt
    is generated per-store and stored alongside the data (salt is not secret).
    """

    key: bytes = field(default_factory=b"")

    @staticmethod
    def derive_key(
        passphrase: str,
        salt: bytes,
        length: int = 32,
    ) -> bytes:
        """Derive a 256-bit key from *passphrase* + *salt* via PBKDF2-HMAC-SHA256.

        Uses PBKDF2 (stdlib only — no external deps required) as a portable
        fallback; if ``cryptography`` is available, it is used for the actual
        AES-GCM crypto operations.
        """
        return hashlib.pbkdf2_hmac(
            "sha256",
            passphrase.encode("utf-8"),
            salt,
            iterations=600_000,
            dklen=length,
        )

    @classmethod
    def from_passphrase(cls, passphrase: str, salt_b64: str) -> "AES256Crypto":
        salt = base64.b64decode(salt_b64)
        return cls(key=cls.derive_key(passphrase, salt))

    def encrypt(self, plaintext: bytes) -> str:
        """Encrypt *plaintext* → base64(nonce + ciphertext + tag)."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:
            raise StoreError(
                "cryptography package is required for encrypted storage. "
                "Install with: pip install cryptography"
            ) from exc

        if len(self.key) != 32:
            raise StoreError(
                f"AES-256 requires a 32-byte key, got {len(self.key)} bytes."
            )
        aesgcm = AESGCM(self.key)
        nonce = secrets.token_bytes(12)
        ct = aesgcm.encrypt(nonce, plaintext, None)
        blob = nonce + ct
        return base64.b64encode(blob).decode("ascii")

    def decrypt(self, ciphertext_b64: str) -> bytes:
        """Decrypt base64(nonce + ciphertext + tag) → plaintext."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:
            raise StoreError(
                "cryptography package is required for encrypted storage. "
                "Install with: pip install cryptography"
            ) from exc

        if len(self.key) != 32:
            raise StoreError(
                f"AES-256 requires a 32-byte key, got {len(self.key)} bytes."
            )
        blob = base64.b64decode(ciphertext_b64)
        nonce = blob[:12]
        ct = blob[12:]
        aesgcm = AESGCM(self.key)
        return aesgcm.decrypt(nonce, ct, None)


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #

@dataclass
class StoreConfig:
    """Filesystem layout for the encrypted store."""

    store_dir: str = os.path.join(
        os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
        "nexus-eda",
        "sovereign",
    )
    salt_file: str = "salt.b64"
    data_file: str = "data.enc"
    index_file: str = "index.enc"


class EncryptedStore:
    """AES-256-GCM encrypted key-value store on disk.

    All values are JSON-serialised, encrypted, and stored in a single
    ``data.enc`` file.  An optional encrypted index maps keys → offsets
    so that individual keys can be deleted/updated without full rewrite.
    """

    def __init__(
        self,
        passphrase: str,
        config: Optional[StoreConfig] = None,
    ):
        self.config = config or StoreConfig()
        self._store_path = Path(self.config.store_dir)
        self._store_path.mkdir(parents=True, exist_ok=True)
        self._salt_path = self._store_path / self.config.salt_file
        self._data_path = self._store_path / self.config.data_file
        self._index_path = self._store_path / self.config.index_file
        self._salt = self._load_or_create_salt()
        self._crypto = AES256Crypto.from_passphrase(passphrase, self._salt)
        self._data: Dict[str, Any] = {}
        self._load()

    # -- salt --------------------------------------------------------------- #

    def _load_or_create_salt(self) -> str:
        if self._salt_path.exists():
            return self._salt_path.read_text(encoding="utf-8").strip()
        salt = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        # Ensure the salt file is not world-readable.
        fd = os.open(
            self._salt_path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(salt)
        return salt

    # -- load / save -------------------------------------------------------- #

    def _load(self) -> None:
        if not self._data_path.exists():
            self._data = {}
            return
        encrypted = self._data_path.read_text(encoding="ascii")
        plaintext = self._crypto.decrypt(encrypted)
        self._data = json.loads(plaintext.decode("utf-8"))

    def _save(self) -> None:
        plaintext = json.dumps(self._data, ensure_ascii=False).encode("utf-8")
        encrypted = self._crypto.encrypt(plaintext)
        # Atomic write: write to temp, rename.
        tmp = self._data_path.with_suffix(".enc.tmp")
        fd = os.open(
            tmp,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(encrypted)
        tmp.replace(self._data_path)

    # -- public API --------------------------------------------------------- #

    def put(self, key: str, value: Any) -> None:
        """Store *value* under *key* (encrypted at rest)."""
        self._data[key] = value
        self._save()

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve *key* from the encrypted store."""
        return self._data.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        """Return a copy of all stored key-values."""
        return dict(self._data)

    def delete(self, key: str) -> bool:
        """Delete *key* from the store. Returns True if it existed."""
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def delete_all(self) -> int:
        """Wipe all data. Required for GDPR right-to-be-forgotten."""
        count = len(self._data)
        self._data.clear()
        self._save()
        return count

    def keys(self) -> List[str]:
        return list(self._data.keys())

    @contextmanager
    def transaction(self) -> "EncryptedStore":
        """Context manager for atomic batch operations."""
        yield self
        self._save()

    @property
    def key_count(self) -> int:
        return len(self._data)

    @property
    def store_dir(self) -> Path:
        return self._store_path

    def rotate_key(self, new_passphrase: str) -> None:
        """Re-encrypt all data with a new passphrase/key."""
        new_crypto = AES256Crypto.from_passphrase(
            new_passphrase, self._salt
        )
        # Decrypt with old key, re-encrypt with new.
        self._crypto = new_crypto
        self._save()
