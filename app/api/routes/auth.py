from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.core.auth_sessions import build_auth_session_service
from app.repositories.auth_sessions import (
    AuthSessionNotFoundError,
    AuthSessionStorageError,
)
from app.schemas.auth import AuthSessionResponse, SessionPrincipal
from app.services.auth_sessions import AuthSessionService


SESSION_COOKIE_NAME = "finshield_session"

router = APIRouter(prefix="/auth", tags=["auth"])

_service = build_auth_session_service()


def get_auth_session_service() -> AuthSessionService:
    return _service


def verify_auth_session_storage() -> None:
    _service.verify_storage()


AuthServiceDependency = Annotated[
    AuthSessionService,
    Depends(get_auth_session_service),
]
SessionCookie = Annotated[
    str | None,
    Cookie(alias=SESSION_COOKIE_NAME),
]


def get_current_session(
    service: AuthServiceDependency,
    session_token: SessionCookie = None,
) -> SessionPrincipal:
    if not session_token:
        raise _unauthorized()
    try:
        return service.authenticate(session_token)
    except AuthSessionNotFoundError as exc:
        raise _unauthorized() from exc
    except AuthSessionStorageError as exc:
        raise _storage_unavailable() from exc


CurrentSessionDependency = Annotated[
    SessionPrincipal,
    Depends(get_current_session),
]


@router.post(
    "/session",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    response: Response,
    service: AuthServiceDependency,
    session_token: SessionCookie = None,
) -> AuthSessionResponse:
    try:
        issue = service.bootstrap(session_token)
    except AuthSessionStorageError as exc:
        raise _storage_unavailable() from exc

    if issue.raw_token is not None:
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=issue.raw_token,
            max_age=service.ttl_seconds,
            httponly=True,
            secure=service.cookie_secure,
            samesite="strict",
            path="/",
        )
    return _response(issue.principal)


@router.get("/session", response_model=AuthSessionResponse)
def read_session(
    principal: CurrentSessionDependency,
) -> AuthSessionResponse:
    return _response(principal)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    response: Response,
    principal: CurrentSessionDependency,
    service: AuthServiceDependency,
    session_token: SessionCookie = None,
) -> None:
    del principal
    try:
        service.revoke(session_token)
    except AuthSessionStorageError as exc:
        raise _storage_unavailable() from exc
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=service.cookie_secure,
        samesite="strict",
    )


def _response(principal: SessionPrincipal) -> AuthSessionResponse:
    return AuthSessionResponse(
        user_id=principal.user_id,
        expires_at=principal.expires_at,
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication required",
        headers={"WWW-Authenticate": "Session"},
    )


def _storage_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="authentication storage unavailable",
    )
