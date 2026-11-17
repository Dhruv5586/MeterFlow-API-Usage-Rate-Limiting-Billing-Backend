"""
Authentication Schemas
----------------------
Pydantic validation models for user registration, user login, and JWT token issuance.
"""

from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.schemas.user import UserResponse


class RegisterRequest(BaseModel):
    email: EmailStr = Field(description="Unique email address for the user account")
    password: str = Field(min_length=8, max_length=128, description="Plaintext password (at least 8 characters)")
    display_name: str = Field(min_length=2, max_length=100, description="Organization or developer display name")

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("display_name", mode="after")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Display name cannot be blank or whitespace only.")
        return clean


class LoginRequest(BaseModel):
    email: EmailStr = Field(description="Registered email address")
    password: str = Field(description="Account password")

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    access_token: str = Field(description="Cryptographically signed JWT Bearer token")
    token_type: str = Field(default="bearer", description="Token scheme (Bearer)")
    expires_in: int = Field(description="Seconds until token expiration")
    user: UserResponse = Field(description="Basic profile info for the authenticated user")
