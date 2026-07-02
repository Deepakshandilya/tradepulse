"""
Utility for encrypting and decrypting sensitive credentials.
"""
import os
from cryptography.fernet import Fernet
from config import Config

# Initialize Fernet globally with the key from config
_key = Config.CREDENTIAL_ENCRYPTION_KEY
if not _key:
    # We fallback to a dummy key to prevent startup crash during dev/migrations, 
    # but actual encryption/decryption will fail or use this dummy one.
    _key = Fernet.generate_key().decode()
    
fernet = Fernet(_key.encode())

def encrypt_password(plain: str) -> bytes:
    """Encrypt a plaintext string."""
    if not plain:
        return b""
    return fernet.encrypt(plain.encode())

def decrypt_password(token: bytes) -> str:
    """Decrypt an encrypted token back to plaintext string."""
    if not token:
        return ""
    return fernet.decrypt(token).decode()
