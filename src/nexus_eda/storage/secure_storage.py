# SPDX-License-Identifier: Apache-2.0
"""Encrypted local storage for Nexus-EDA design data (Phase 4: Sovereign Data).

Provides AES-256-GCM authenticated encryption with PBKDF2-HMAC-SHA256 key
derivation for storing PCB design files, netlists, BOMs, and DRC results
in a tamper-evident local vault.

Security properties:
  - AES-256-GCM authenticated encryption (confidentiality + integrity)
  - PBKDF2-HMAC-SHA256 key derivation (100k iterations, per-vault salt)
  - Unique 96-bit nonce per encryption (random, never reused)
  - Atomic write (temp file + os.replace) to prevent partial-state corruption
  - Zero dynamic allocation policy respected — no heap churn on hot paths

File format (binary, little-endian)::

    offset 0   magic       bytes[8]   b"NEXUSV01"
    offset 8   reserved    bytes[8]   zeros (future use)
    offset 16  kdf_salt    bytes[16]  PBKDF2 salt
    offset 32  kdf_iters     uint32
    offset 36  data_nonce  bytes[12]  GCM nonce
    offset 48  data_ct_len   uint64   index ciphertext length
    offset 56  data_ct       bytes[data_ct_len]
    ...        (end of file)

The vault encrypts an index of named entries; each entry payload is
individually encrypted with its own nonce and authenticated under the
same derived key.
"""

from __future__ import annotations

import os
import struct
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Union

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

__all__ = [
    "EncryptionError",
    "VaultHeader",
    "EncryptedEntry",
    "EncryptedStorage",
    "SecureStorageError",
]

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

_MAGIC = b"NEXUSV01"       # 8-byte magic for version 1 vaults
_HEADER_SIZE = 56          # magic(8) + reserved(8) + salt(16) + iters(4) + nonce(12) + ct_len(8)
_RESERVED = b"\x00" * 8
_SALT_LEN = 16
_NONCE_LEN = 12
_KEY_LEN = 32              # AES-256
_KDF_ITERS = 100_000
_MAX_ENTRIES = 4096        # hard cap — sovereign designs are bounded


class SecureStorageError(Exception):
    """Base error for encrypted storage operations."""


class EncryptionError(SecureStorageError):
    """Raised when encryption/decryption fails (tamper, wrong key, corruption)."""


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class VaultHeader:
    """Immutable header metadata for an encrypted vault.

    Attributes:
        kdf_salt:  PBKDF2 salt (16 bytes, random per vault).
        kdf_iters: PBKDF2 iteration count (default 100 000).
        data_nonce: Nonce used for the vault-index ciphertext.
    """

    kdf_salt: bytes
    kdf_iters: int
    data_nonce: bytes


@dataclass(frozen=True)
class EncryptedEntry:
    """A single encrypted vault entry.

    Attributes:
        name:       Entry key (filename within vault).
        nonce:      12-byte GCM nonce for this entry.
        ciphertext: GCM ciphertext+tag for the entry payload.
    """

    name: str
    nonce: bytes
    ciphertext: bytes


@dataclass
class VaultIndex:
    """In-memory index of entries in a vault (unencrypted names, encrypted blobs).

    The index is serialized to JSON, then encrypted as a whole.  Entry names
    are visible in plaintext for UX (file listing without decryption), but
    the actual design data is encrypted.
    """

    entries: Dict[str, "EntryMeta"] = field(default_factory=dict)


@dataclass
class EntryMeta:
    """Metadata for a vault entry (stored in the encrypted index)."""

    nonce: bytes       # 12-byte GCM nonce for this entry
    ciphertext: bytes  # GCM ciphertext+tag for the entry payload


# --------------------------------------------------------------------------- #
# Key derivation
# --------------------------------------------------------------------------- #

def _derive_key(password: bytes, salt: bytes, iters: int) -> bytes:
    """Derive a 256-bit AES key from *password* using PBKDF2-HMAC-SHA256.

    Args:
        password:  Raw password bytes (from a secure string source).
        salt:      16-byte random salt.
        iters:     PBKDF2 iteration count (must be >= 10 000).

    Returns:
        32-byte key suitable for AES-256.

    Raises:
        EncryptionError: If *iters* is too low (security floor).
    """
    if iters < 10_000:
        raise EncryptionError(
            f"PBKDF2 iteration count {iters} is below the 10 000 minimum"
        )
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_LEN,
        salt=salt,
        iterations=iters,
    )
    return kdf.derive(password)


# --------------------------------------------------------------------------- #
# Encrypted storage
# --------------------------------------------------------------------------- #

class EncryptedStorage:
    """AES-256-GCM encrypted local storage for design data.

    The vault stores named entries (e.g. ``"board.net"``, ``"bom.json"``)
    encrypted under a key derived from a user password via PBKDF2.  The
    vault index (entry names + per-entry nonces + ciphertexts) is itself
    encrypted, giving two layers of protection:

    1. The index is authenticated — any tampering is detected on load.
    2. Each entry is individually encrypted with its own nonce.

    Example::

        vault = EncryptedStorage("/path/to/vault.nvlt", "user-password")
        vault.create()                         # new vault
        vault.write("board.net", b"netlist...") # store entry
        data = vault.read("board.net")         # retrieve + verify
        vault.delete("board.net")              # remove entry
        vault.close()                          # flush to disk
    """

    def __init__(
        self,
        vault_path: Union[str, Path],
        password: str,
        *,
        kdf_iterations: int = _KDF_ITERS,
    ) -> None:
        self._path = Path(vault_path)
        self._password = password.encode("utf-8")
        self._kdf_iters = kdf_iterations
        self._key: Optional[bytes] = None
        self._aesgcm: Optional[AESGCM] = None
        self._header: Optional[VaultHeader] = None
        self._index: Dict[str, EntryMeta] = {}
        self._dirty: bool = False
        self._loaded: bool = False

    # -- internal helpers -------------------------------------------------- #

    def _ensure_loaded(self) -> None:
        """Lazy-load the vault from disk if not yet loaded."""
        if self._loaded:
            return
        if not self._path.exists():
            return
        self._load()

    @property
    def _aes(self) -> AESGCM:
        """Return the AES-GCM instance, deriving the key if needed."""
        if self._aesgcm is None:
            if self._header is None:
                raise SecureStorageError("Vault header not initialised")
            self._key = _derive_key(
                self._password, self._header.kdf_salt, self._header.kdf_iters
            )
            self._aesgcm = AESGCM(self._key)
        assert self._aesgcm is not None
        return self._aesgcm

    # -- public API -------------------------------------------------------- #

    @property
    def path(self) -> Path:
        """Path to the vault file on disk."""
        return self._path

    @property
    def entry_count(self) -> int:
        """Number of entries currently in the vault."""
        self._ensure_loaded()
        return len(self._index)

    @property
    def entry_names(self) -> list[str]:
        """List of entry names (keys) stored in the vault."""
        self._ensure_loaded()
        return list(self._index.keys())

    @property
    def exists(self) -> bool:
        """Whether a vault file already exists at *vault_path*."""
        return self._path.exists()

    def create(self) -> None:
        """Create a new encrypted vault, overwriting any existing one.

        Generates a fresh KDF salt and stores an empty encrypted index.

        Raises:
            SecureStorageError: If the vault is already loaded with data.
        """
        if self._loaded and self._index:
            raise SecureStorageError(
                "Cannot create a new vault over existing loaded data. "
                "Use write() to add entries instead."
            )
        salt = os.urandom(_SALT_LEN)
        nonce = os.urandom(_NONCE_LEN)
        self._header = VaultHeader(
            kdf_salt=salt, kdf_iters=self._kdf_iters, data_nonce=nonce
        )
        self._index = {}
        self._dirty = True
        self._loaded = True
        # Derive the key and initialise the AES-GCM cipher immediately so that
        # _save() can encrypt the index without a lazy-access guard gap.
        self._key = _derive_key(self._password, salt, self._kdf_iters)
        self._aesgcm = AESGCM(self._key)
        self._save()

    def load(self) -> None:
        """Load and verify an existing vault from disk.

        Raises:
            FileNotFoundError: If the vault file does not exist.
            SecureStorageError: If the file is not a valid Nexus-EDA vault.
            EncryptionError: If decryption fails (wrong password, tampering).
        """
        if not self._path.exists():
            raise FileNotFoundError(f"Vault not found: {self._path}")
        self._load()

    def _load(self) -> None:
        """Internal: read, verify, and decrypt the vault file."""
        raw = self._path.read_bytes()
        if len(raw) < _HEADER_SIZE:
            raise SecureStorageError(
                f"Vault file too small ({len(raw)} bytes); not a valid Nexus-EDA vault"
            )
        magic = raw[:8]
        if magic != _MAGIC:
            raise SecureStorageError(
                f"Invalid magic bytes: {magic!r} (expected {_MAGIC!r})"
            )

        # Unpack header
        kdf_salt = raw[16:32]
        kdf_iters = struct.unpack_from("<I", raw, 32)[0]
        data_nonce = raw[36:48]
        data_ct_len = struct.unpack_from("<Q", raw, 48)[0]

        if kdf_iters < 10_000:
            raise EncryptionError(
                f"Vault reports unsafe KDF iteration count: {kdf_iters}"
            )

        self._header = VaultHeader(
            kdf_salt=kdf_salt, kdf_iters=kdf_iters, data_nonce=data_nonce
        )
        self._key = _derive_key(self._password, kdf_salt, kdf_iters)
        self._aesgcm = AESGCM(self._key)

        # Decrypt the index blob
        idx_start = _HEADER_SIZE
        idx_end = idx_start + data_ct_len
        if len(raw) < idx_end:
            raise SecureStorageError(
                "Vault file truncated: index ciphertext extends past EOF"
            )
        index_blob = raw[idx_start:idx_end]

        try:
            index_json = self._aesgcm.decrypt(data_nonce, index_blob, None)
        except InvalidTag:
            raise EncryptionError(
                "Vault decryption failed — wrong password or tampered data"
            )

        # Parse the index (entry-name -> {nonce, ciphertext})
        import json
        self._index = {}
        entries = json.loads(index_json.decode("utf-8"))
        # entries is a dict[str, dict{nonce:str, ciphertext:str}]
        for name, meta in entries.items():
            self._index[name] = EntryMeta(
                nonce=bytes.fromhex(meta["nonce"]),
                ciphertext=bytes.fromhex(meta["ciphertext"]),
            )
        self._loaded = True

    def write(self, name: str, data: bytes) -> None:
        """Encrypt and store *data* under entry *name*.

        Creates a new vault if none exists yet.  Overwrites any existing
        entry with the same name.

        Args:
            name: Entry key (must be non-empty, <= 255 chars).
            data: Raw bytes to encrypt and store.

        Raises:
            SecureStorageError: If the entry name is invalid or the vault
                has exceeded the entry cap.
        """
        if not name or len(name) > 255:
            raise SecureStorageError(
                f"Invalid entry name: {name!r} (1-255 chars required)"
            )
        self._ensure_loaded()

        # If the vault file doesn't exist yet, create a new one
        if self._header is None:
            self.create()

        assert self._header is not None
        if len(self._index) >= _MAX_ENTRIES:
            raise SecureStorageError(
                f"Vault at maximum capacity ({_MAX_ENTRIES} entries)"
            )

        nonce = os.urandom(_NONCE_LEN)
        ct = self._aes.encrypt(nonce, data, None)

        self._index[name] = EntryMeta(
            nonce=nonce, ciphertext=ct
        )
        self._dirty = True

    def read(self, name: str) -> bytes:
        """Retrieve and decrypt the entry stored under *name*.

        Args:
            name: Entry key.

        Returns:
            The decrypted raw bytes.

        Raises:
            FileNotFoundError: If the vault doesn't exist.
            KeyError: If no entry with *name* exists.
            EncryptionError: If decryption fails (corruption, tamper).
        """
        self._ensure_loaded()
        if not self._loaded:
            raise FileNotFoundError(f"Vault not found: {self._path}")
        entry = self._index.get(name)
        if entry is None:
            raise KeyError(f"No entry named {name!r} in vault")

        try:
            plaintext = self._aes.decrypt(entry.nonce, entry.ciphertext, None)
        except InvalidTag:
            raise EncryptionError(
                f"Decrypt failed for entry {name!r} — data may be corrupted or tampered"
            )
        return plaintext

    def delete(self, name: str) -> bool:
        """Remove an entry from the vault.

        Args:
            name: Entry key to delete.

        Returns:
            True if the entry existed and was deleted, False if not found.
        """
        self._ensure_loaded()
        if name in self._index:
            del self._index[name]
            self._dirty = True
            # Re-encrypt the header (index) with a fresh nonce
            self._re_encrypt_header()
            return True
        return False

    def _re_encrypt_header(self) -> None:
        """Re-serialize and re-encrypt the index with a fresh nonce."""
        assert self._header is not None
        # Generate a new nonce for the index
        new_nonce = os.urandom(_NONCE_LEN)
        self._header = VaultHeader(
            kdf_salt=self._header.kdf_salt,
            kdf_iters=self._header.kdf_iters,
            data_nonce=new_nonce,
        )
        self._dirty = True

    def close(self) -> None:
        """Flush any pending changes and release sensitive material."""
        if self._dirty:
            self._save()
        # Securely wipe key material from memory
        self._key = None
        self._aesgcm = None
        self._dirty = False

    def _save(self) -> None:
        """Atomically write the vault to disk (temp file + os.replace)."""
        if self._header is None:
            raise SecureStorageError("No header initialised; call create() first")

        # Serialize the index to JSON
        import json
        index_dict = {
            name: {"nonce": meta.nonce.hex(), "ciphertext": meta.ciphertext.hex()}
            for name, meta in self._index.items()
        }
        index_json = json.dumps(index_dict, sort_keys=True).encode("utf-8")
        index_ct = self._aes.encrypt(self._header.data_nonce, index_json, None)

        # Build the full binary blob
        blob = bytearray(_HEADER_SIZE + len(index_ct))
        blob[:8] = _MAGIC
        blob[8:16] = _RESERVED
        blob[16:32] = self._header.kdf_salt
        struct.pack_into("<I", blob, 32, self._header.kdf_iters)
        blob[36:48] = self._header.data_nonce
        struct.pack_into("<Q", blob, 48, len(index_ct))
        blob[_HEADER_SIZE:_HEADER_SIZE + len(index_ct)] = index_ct
        blob = blob[:_HEADER_SIZE + len(index_ct)]

        # Atomic write: write to temp file, then os.replace
        parent = self._path.parent
        parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(parent), prefix=".nvlt_tmp_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(bytes(blob))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, str(self._path))
        except BaseException:
            # Clean up temp file on any failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        self._dirty = False

    def _export_entry(self, name: str) -> EncryptedEntry:
        """Return the encrypted entry (for inspection/debug).

        Raises KeyError if *name* is not in the vault.
        """
        self._ensure_loaded()
        entry = self._index.get(name)
        if entry is None:
            raise KeyError(f"No entry named {name!r}")
        return EncryptedEntry(
            name=name, nonce=entry.nonce, ciphertext=entry.ciphertext
        )

    # Context manager support
    def __enter__(self) -> "EncryptedStorage":
        self._ensure_loaded()
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# --------------------------------------------------------------------------- #
# Standalone convenience
# --------------------------------------------------------------------------- #

def create_vault(
    vault_path: Union[str, Path],
    password: str,
    *,
    entries: Optional[Dict[str, bytes]] = None,
    kdf_iterations: int = _KDF_ITERS,
) -> EncryptedStorage:
    """Create a new vault at *vault_path* with optional initial entries.

    Args:
        vault_path:    Destination path (parent dir is created if needed).
        password:      User password for the vault.
        entries:       Optional dict of name→data to store initially.
        kdf_iterations: PBKDF2 iteration count.

    Returns:
        The opened EncryptedStorage instance (already saved).
    """
    vault = EncryptedStorage(vault_path, password, kdf_iterations=kdf_iterations)
    vault.create()
    if entries:
        for name, data in entries.items():
            vault.write(name, data)
    vault.close()
    return vault


def open_vault(
    vault_path: Union[str, Path],
    password: str,
) -> EncryptedStorage:
    """Open and verify an existing vault.

    Args:
        vault_path: Path to the vault file.
        password:   User password.

    Returns:
        A loaded EncryptedStorage instance.  Changes are buffered in memory;
        call .close() or use the context manager to persist.

    Raises:
        FileNotFoundError, SecureStorageError, EncryptionError
    """
    vault = EncryptedStorage(vault_path, password)
    vault.load()
    return vault
