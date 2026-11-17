"""
Domain & Application Exceptions
-------------------------------
Custom exception hierarchy for MeterFlow to decouple business rules from HTTP codes.
"""

from typing import Optional, Any, Dict


class MeterFlowException(Exception):
    """Base exception for all MeterFlow application errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class DatabaseConnectionError(MeterFlowException):
    """Raised when the database cannot be reached or health check fails."""
    pass


class EntityNotFoundError(MeterFlowException):
    """Raised when a requested resource (e.g., User, Plan, Event) does not exist."""
    def __init__(self, entity_name: str, entity_id: Any):
        message = f"{entity_name} with identifier '{entity_id}' was not found."
        super().__init__(message, details={"entity": entity_name, "id": str(entity_id)})
        self.entity_name = entity_name
        self.entity_id = entity_id


class EntityConflictError(MeterFlowException):
    """Raised when an operation would violate a uniqueness constraint."""
    pass


class InvalidParameterError(MeterFlowException):
    """Raised when query or body parameters fail business domain validation."""
    pass


class AuthenticationError(MeterFlowException):
    """Raised when authentication fails (missing, invalid, or expired credentials)."""
    pass


class AuthorizationError(MeterFlowException):
    """Raised when an authenticated entity lacks permission to access a resource."""
    pass


class InvalidAPIKeyError(AuthenticationError):
    """Raised when an API key is missing, malformed, inactive, expired, or revoked."""
    pass


class RateLimitExceededError(MeterFlowException):
    """
    Raised when a tenant exceeds their allowed rate limit (HTTP 429).
    Carries window limit and reset seconds for standard header population.
    """
    def __init__(
        self,
        message: str = "Rate limit exceeded. Please try again later.",
        limit: int = 60,
        remaining: int = 0,
        reset_seconds: int = 60,
        retry_after: int = 60,
    ):
        super().__init__(
            message=message,
            details={
                "limit": limit,
                "remaining": remaining,
                "reset_seconds": reset_seconds,
                "retry_after": retry_after,
            },
        )
        self.limit = limit
        self.remaining = remaining
        self.reset_seconds = reset_seconds
        self.retry_after = retry_after
