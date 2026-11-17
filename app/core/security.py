"""
Security Utilities: Bcrypt Hashing, JWT Tokens, and API Key Cryptography
------------------------------------------------------------------------
Implements:
1. Secure password hashing with bcrypt (work factor / cost 12).
2. JWT token issuance and signature verification (PyJWT).
3. Cryptographically strong API key generation (secrets module) and SHA-256 hashing.
"""

import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any
import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import AuthenticationError


# -----------------------------------------------------------------------------
# 1. Password Hashing & Verification (Bcrypt)
# -----------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """
    Hashes a plaintext password using bcrypt with a generated salt.
    Enforces UTF-8 encoding and returns the salt + hash as a string.
    """
    if not password:
        raise ValueError("Password cannot be empty.")
    
    salt = bcrypt.gensalt(rounds=12)
    pwd_bytes = password.encode("utf-8")
    hashed_bytes = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plaintext password against a stored hash.
    Safely handles standard bcrypt hashes and fallback demo hashes.
    """
    if not plain_password or not hashed_password:
        return False

    try:
        # Standard bcrypt verification
        if hashed_password.startswith("$2b$") or hashed_password.startswith("$2a$") or hashed_password.startswith("$2y$"):
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        
        # Fallback for demo accounts seeded with sha256 hex digests
        plain_sha256 = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
        return secrets.compare_digest(plain_sha256, hashed_password)
    except Exception:
        return False


# -----------------------------------------------------------------------------
# 2. JWT Access Tokens (PyJWT)
# -----------------------------------------------------------------------------

def create_access_token(
    subject: str,
    claims: Optional[Dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None,
) -> Tuple[str, int]:
    """
    Generates a cryptographically signed JWT access token.
    Returns:
        (token_string, expires_in_seconds)
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    expires_in_seconds = int((expire - now).total_seconds())

    payload = {
        "sub": str(subject),
        "iat": now,
        "exp": expire,
        "iss": settings.APP_NAME,
        "type": "access",
    }
    if claims:
        payload.update(claims)

    encoded_jwt = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt, expires_in_seconds


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates a JWT access token.
    Raises AuthenticationError if expired or malformed.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.APP_NAME,
            options={"require": ["sub", "exp", "iat"]},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Access token has expired. Please log in again.")
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError(f"Invalid access token: {str(exc)}")


# -----------------------------------------------------------------------------
# 3. API Key Cryptography (secrets + SHA-256)
# -----------------------------------------------------------------------------

def generate_api_key(environment: str = "live") -> Tuple[str, str, str]:
    """
    Generates a cryptographically random API key.
    
    Structure:
        - Full key: mf_<env>_<43 urlsafe random characters>
        - Key prefix: first 16 characters (e.g., mf_live_AbC123...)
        - Key hash: lowercase 64-char hexadecimal SHA-256 digest
    
    Returns:
        (full_plaintext_key, key_prefix, key_hash_hex)
    """
    # 32 bytes of secure entropy = 43 URL-safe base64 characters
    random_entropy = secrets.token_urlsafe(32)
    full_key = f"mf_{environment}_{random_entropy}"
    prefix = full_key[:16]
    key_hash = hash_api_key(full_key)

    return full_key, prefix, key_hash


def hash_api_key(plain_key: str) -> str:
    """
    Produces the standard lowercase 64-character SHA-256 hex digest
    conforming strictly to: CHECK (key_hash ~ '^[0-9a-f]{64}$')
    """
    return hashlib.sha256(plain_key.strip().encode("utf-8")).hexdigest().lower()
