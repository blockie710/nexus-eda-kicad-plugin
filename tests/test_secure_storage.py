# SPDX-License-Identifier: Apache-2.0
"""Unit tests for encrypted local storage (Phase 4 — Sovereign Data)."""

import os
import tempfile
import struct
from pathlib import Path

import pytest

from nexus_eda.storage.secure_storage import (
    EncryptedStorage,
    EncryptionError,
    SecureStorageError,
    create_vault,
    open_vault,
    _MAGIC,
    _HEADER_SIZE,
    _SALT_LEN,
    _NONCE_LEN,
    _KDF_ITERS,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def tmp_vault_path():
    """Provide a temporary vault path that is cleaned up after the test."""
    fd, path = tempfile.mkstemp(suffix=".nvlt")
    os.close(fd)
    os.unlink(path)  # remove so the vault starts fresh
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def created_vault(tmp_vault_path):
    """Create a vault with a known password and return (path, password)."""
    pw = "S0v31gn_P@ss!"
    vault = create_vault(tmp_vault_path, pw)
    assert vault.exists
    return tmp_vault_path, pw


# --------------------------------------------------------------------------- #
# Creation & loading
# --------------------------------------------------------------------------- #

def test_create_vault_creates_file(tmp_vault_path):
    """create_vault writes a file with the correct magic bytes."""
    pw = "test-password-123"
    vault = create_vault(tmp_vault_path, pw)
    assert vault.exists
    raw = Path(tmp_vault_path).read_bytes()
    assert raw[:8] == _MAGIC
    vault.close()


def test_open_vault_loads_existing(created_vault):
    """open_vault returns a vault with the same entry count."""
    path, pw = created_vault
    vault = open_vault(path, pw)
    assert vault.entry_count == 0
    assert vault.entry_names == []
    vault.close()


def test_open_vault_wrong_password_fails(created_vault):
    """Wrong password triggers an EncryptionError."""
    path, _ = created_vault
    with pytest.raises(EncryptionError):
        open_vault(path, "wrong-password")


def test_open_vault_file_not_found():
    """Opening a nonexistent vault raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        open_vault("/nonexistent/path/to.vault", "pw")


# --------------------------------------------------------------------------- #
# Write & read round-trip
# --------------------------------------------------------------------------- #

def test_write_and_read_single_entry(tmp_vault_path):
    """A single entry can be written and read back correctly."""
    pw = "round-trip-pw"
    vault = EncryptedStorage(tmp_vault_path, pw)
    vault.create()
    vault.write("board.net", b"(kicad_netlist (version 20211014))")
    # Flush by re-loading from disk in a fresh object
    vault.close()

    # Re-open and read
    vault2 = EncryptedStorage(tmp_vault_path, pw)
    vault2.load()
    assert vault2.entry_count == 1
    assert vault2.entry_names == ["board.net"]
    data = vault2.read("board.net")
    assert data == b"(kicad_netlist (version 20211014))"
    vault2.close()


def test_write_and_read_multiple_entries(tmp_vault_path):
    """Multiple entries are stored and retrieved independently."""
    pw = "multi-pw"
    vault = EncryptedStorage(tmp_vault_path, pw)
    vault.create()
    vault.write("board.net", b"netlist-data")
    vault.write("bom.json", b'{"parts": []}')
    vault.write("drc.txt", b"DRC: no violations")

    vault.close()

    # Fresh load
    vault2 = open_vault(tmp_vault_path, pw)
    assert vault2.entry_count == 3
    assert set(vault2.entry_names) == {"board.net", "bom.json", "drc.txt"}
    assert vault2.read("board.net") == b"netlist-data"
    assert vault2.read("bom.json") == b'{"parts": []}'
    assert vault2.read("drc.txt") == b"DRC: no violations"
    vault2.close()


def test_read_nonexistent_entry_raises_keyerror(tmp_vault_path):
    """Reading an absent entry raises KeyError, not a crypto error."""
    pw = "pw"
    vault = EncryptedStorage(tmp_vault_path, pw)
    vault.create()
    vault.write("exists", b"data")
    with pytest.raises(KeyError):
        vault.read("does-not-exist")
    vault.close()


def test_overwrite_existing_entry(tmp_vault_path):
    """Writing the same name twice stores the latest data."""
    pw = "pw"
    vault = EncryptedStorage(tmp_vault_path, pw)
    vault.create()
    vault.write("key", b"original")
    vault.write("key", b"updated")
    assert vault.entry_count == 1
    assert vault.read("key") == b"updated"
    vault.close()


# --------------------------------------------------------------------------- #
# Delete
# --------------------------------------------------------------------------- #

def test_delete_existing_entry(tmp_vault_path):
    """Deleting an existing entry returns True and removes it."""
    pw = "pw"
    vault = EncryptedStorage(tmp_vault_path, pw)
    vault.create()
    vault.write("keep", b"data")
    vault.write("drop", b"data")
    assert vault.entry_count == 2
    result = vault.delete("drop")
    assert result is True
    assert vault.entry_count == 1
    assert "drop" not in vault.entry_names
    assert "keep" in vault.entry_names
    vault.close()


def test_delete_nonexistent_entry_returns_false(tmp_vault_path):
    """Deleting a missing entry returns False."""
    pw = "pw"
    vault = EncryptedStorage(tmp_vault_path, pw)
    vault.create()
    result = vault.delete("nope")
    assert result is False
    vault.close()


# --------------------------------------------------------------------------- #
# Tamper detection
# --------------------------------------------------------------------------- #

def test_tampered_vault_fails_auth(tmp_vault_path):
    """Flipping a byte in the ciphertext triggers an EncryptionError."""
    pw = "pw"
    vault = create_vault(tmp_vault_path, pw, entries={"secret": b"top-secret-data"})
    vault.close()

    # Flip a byte at the end of the file (in the index ciphertext)
    raw = bytearray(Path(tmp_vault_path).read_bytes())
    raw[-1] ^= 0xFF
    Path(tmp_vault_path).write_bytes(raw)

    with pytest.raises(EncryptionError):
        open_vault(tmp_vault_path, pw)


def test_corrupted_header_fails(tmp_vault_path):
    """Truncated vault (too small) raises SecureStorageError."""
    pw = "pw"
    create_vault(tmp_vault_path, pw)
    Path(tmp_vault_path).write_bytes(b"NEXUSV01")  # only 8 bytes

    with pytest.raises(SecureStorageError):
        open_vault(tmp_vault_path, pw)


def test_wrong_magic_raises(tmp_vault_path):
    """A file without the NEXUSV01 magic raises SecureStorageError."""
    pw = "pw"
    Path(tmp_vault_path).write_bytes(b"NOTAVAULT" + b"\x00" * 100)
    with pytest.raises(SecureStorageError):
        open_vault(tmp_vault_path, pw)


# --------------------------------------------------------------------------- #
# Entry name validation
# --------------------------------------------------------------------------- #

def test_write_empty_name_rejected(tmp_vault_path):
    """Empty entry names are rejected."""
    pw = "pw"
    vault = EncryptedStorage(tmp_vault_path, pw)
    vault.create()
    with pytest.raises(SecureStorageError):
        vault.write("", b"data")
    vault.close()


def test_write_oversized_name_rejected(tmp_vault_path):
    """Entry names longer than 255 characters are rejected."""
    pw = "pw"
    vault = EncryptedStorage(tmp_vault_path, pw)
    vault.create()
    with pytest.raises(SecureStorageError):
        vault.write("A" * 256, b"data")
    vault.close()


# --------------------------------------------------------------------------- #
# Context manager & auto-load
# --------------------------------------------------------------------------- #

def test_context_manager_writes_and_reads(tmp_vault_path):
    """The context manager auto-loads and flushes on exit."""
    pw = "ctx-pw"
    with EncryptedStorage(tmp_vault_path, pw) as v:
        v.create()
        v.write("ctx-test", b"context-data")

    with EncryptedStorage(tmp_vault_path, pw) as v:
        v.load()
        assert v.read("ctx-test") == b"context-data"


def test_auto_create_on_first_write(tmp_vault_path):
    """write() on a non-existent vault auto-creates it."""
    pw = "auto-pw"
    vault = EncryptedStorage(tmp_vault_path, pw)
    # No create() call — should auto-create
    vault.write("auto_entry", b"auto-data")
    assert vault.exists
    assert vault.entry_count == 1
    vault.close()

    # Verify persistence
    vault2 = open_vault(tmp_vault_path, pw)
    assert vault2.read("auto_entry") == b"auto-data"
    vault2.close()


# --------------------------------------------------------------------------- #
# Large data
# --------------------------------------------------------------------------- #

def test_large_entry_round_trip(tmp_vault_path):
    """Entries up to ~1 MB round-trip correctly."""
    pw = "pw"
    vault = create_vault(tmp_vault_path, pw)
    big_data = b"X" * 1_000_000  # 1 MB
    vault.write("big.bin", big_data)
    vault.close()

    vault2 = open_vault(tmp_vault_path, pw)
    assert vault2.read("big.bin") == big_data
    vault2.close()


def test_binary_data_round_trip(tmp_vault_path):
    """Non-text binary data round-trips correctly."""
    pw = "pw"
    vault = create_vault(tmp_vault_path, pw)
    binary = bytes(range(256)) * 4  # 1024 bytes of all byte values
    vault.write("binary.bin", binary)
    vault.close()

    vault2 = open_vault(tmp_vault_path, pw)
    result = vault2.read("binary.bin")
    assert result == binary
    assert len(result) == 1024
    vault2.close()


# --------------------------------------------------------------------------- #
# Vault format verification
# --------------------------------------------------------------------------- #

def test_vault_header_fields_parsed(tmp_vault_path):
    """The vault header fields are correctly parsed on load."""
    pw = "pw"
    create_vault(tmp_vault_path, pw, entries={"e": b"v"})

    vault = open_vault(tmp_vault_path, pw)
    header = vault._header  # noqa: SLF001 — internal access for test
    assert header is not None
    assert len(header.kdf_salt) == _SALT_LEN
    assert header.kdf_iters == _KDF_ITERS
    assert len(header.data_nonce) == _NONCE_LEN
    vault.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
