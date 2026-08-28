from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import os

print("AES-GCM test")
key = AESGCM.generate_key(bit_length=256)
aesgcm = AESGCM(key)
nonce = os.urandom(12)
ct = aesgcm.encrypt(nonce, b"hello", None)
pt = aesgcm.decrypt(nonce, ct, None)
print(f"Encrypt/decrypt: {pt == b'hello'}")

# PBKDF2 test
kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"salt123", iterations=100000)
derived = kdf.derive(b"password")
print(f"PBKDF2 derive: {len(derived)} bytes")
print("All crypto checks passed")
