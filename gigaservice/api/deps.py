"""
FastAPI dependency injection helpers for authentication and authorization.

Usage:
    # Require any authenticated user
    @router.get("/me")
    async def me(user: dict = Depends(get_current_user)):
        return user

    # Require specific role(s)
    @router.post("/packages/")
    async def create(user: dict = Depends(RoleChecker(["provider", "admin"]))):
        ...
"""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.auth import decode_jwt
from services.attestations import verify_attestation

_bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """Validate the Bearer JWT and return the decoded user dict."""
    try:
        payload = decode_jwt(credentials.credentials)
        return {"address": payload["sub"], "role": payload["role"]}
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


class RoleChecker:
    """Dependency that enforces role-based access control.

    Raises 403 Forbidden when the authenticated user's role is not in
    *allowed_roles*. Raises 401 Unauthorized when no valid JWT is present.
    """

    def __init__(self, allowed_roles: list[str]) -> None:
        self.allowed_roles = allowed_roles

    def __call__(self, user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user['role']}' is not permitted for this action",
            )
        return user


class RequiresAttestation:
    """Dependency that enforces an on-chain EAS attestation.

    Usage::

        SCHEMA_COURIER = "0x" + "ab" * 32  # replace with your real schema UID

        @router.get("/history")
        async def history(
            device_id: str,
            user: dict = Depends(RequiresAttestation(SCHEMA_COURIER)),
        ):
            ...

    Raises 401 Unauthorized when no valid JWT is present.
    Raises 403 Forbidden when the user lacks the required attestation.
    """

    def __init__(self, schema_id: str) -> None:
        self.schema_id = schema_id

    async def __call__(self, user: dict = Depends(get_current_user)) -> dict:
        has_attestation = await verify_attestation(user["address"], self.schema_id)
        if not has_attestation:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required attestation [{self.schema_id}] not found for this address",
            )
        return user
