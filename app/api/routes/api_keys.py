"""
API Key Management Routes
-------------------------
Endpoints for developers to create, list, and revoke their API keys.
Requires Bearer JWT authentication.
"""

import uuid
from typing import List
from fastapi import APIRouter, Depends, status, Path
from app.api.dependencies import get_api_key_service, get_current_user
from app.services.api_key_service import APIKeyService
from app.models.user import User
from app.schemas.api_key import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyResponse,
    APIKeyRevokeResponse,
)

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.get(
    "",
    response_model=List[APIKeyResponse],
    status_code=status.HTTP_200_OK,
    summary="List all API keys for authenticated developer",
    description="Returns all API keys created by the current user, showing key prefixes, expiration status, and revocation timestamps without exposing secrets.",
)
def list_api_keys(
    current_user: User = Depends(get_current_user),
    key_service: APIKeyService = Depends(get_api_key_service),
):
    return key_service.list_keys(current_user.id)


@router.post(
    "",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new high-entropy API key",
    description="Generates a cryptographically random API key (mf_live_...). Plaintext key secret is displayed ONLY ONCE in the response and is never stored.",
)
def create_api_key(
    req: APIKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    key_service: APIKeyService = Depends(get_api_key_service),
):
    return key_service.create_key(user_id=current_user.id, req=req)


@router.delete(
    "/{id}",
    response_model=APIKeyRevokeResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke an existing API key",
    description="Immediately revokes the designated API key. Any future API Gateway requests with this key will be rejected.",
)
def revoke_api_key(
    id: uuid.UUID = Path(..., description="UUID of the API key to revoke"),
    current_user: User = Depends(get_current_user),
    key_service: APIKeyService = Depends(get_api_key_service),
):
    return key_service.revoke_key(key_id=id, user_id=current_user.id)
