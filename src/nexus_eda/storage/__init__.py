# SPDX-License-Identifier: Apache-2.0
"""Encrypted local storage package for Nexus-EDA (Phase 4: Sovereign Data).

Exports the AES-256-GCM vault implementation.
"""

from .secure_storage import (
    EncryptedStorage,
    EncryptedEntry,
    VaultHeader,
    EncryptionError,
    SecureStorageError,
    create_vault,
    open_vault,
)

__all__ = [
    "EncryptedStorage",
    "EncryptedEntry",
    "VaultHeader",
    "EncryptionError",
    "SecureStorageError",
    "create_vault",
    "open_vault",
]
