"""Legacy ECSP V2 verifier derived from EcspUtils/CipherUtils."""
from __future__ import annotations

import hashlib


def upper_md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest().upper()


def upper_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def calculate_ecsp2_auth(username: str, encrypted_password: str, random_key: str) -> str:
    original_auth = username + encrypted_password
    first_hash = upper_sha256(original_auth.encode("utf-8"))
    return upper_sha256((first_hash + random_key).encode("utf-8"))


def calculate_md5_mode_auth(username: str, plain_password: str, random_key: str) -> str:
    return calculate_ecsp2_auth(username, upper_md5(plain_password), random_key)
