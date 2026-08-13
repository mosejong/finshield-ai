from fastapi import APIRouter, HTTPException, Response, status

from app.api.routes.auth import (
    AuthServiceDependency,
    CurrentSessionDependency,
    SESSION_COOKIE_NAME,
    SessionCookie,
)
from app.api.routes.profiles import ProfileServiceDependency
from app.repositories.auth_sessions import (
    AuthSessionNotFoundError,
    AuthSessionStorageError,
)
from app.repositories.financial_profiles import FinancialProfileStorageError


router = APIRouter(prefix="/auth", tags=["auth"])


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_anonymous_account(
    response: Response,
    principal: CurrentSessionDependency,
    auth_service: AuthServiceDependency,
    profile_service: ProfileServiceDependency,
    session_token: SessionCookie = None,
) -> None:
    try:
        profile_service.delete_all_for_owner(principal.user_id)
    except FinancialProfileStorageError as exc:
        raise _deletion_unavailable() from exc

    try:
        auth_service.delete_account(session_token, principal.user_id)
    except AuthSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "Session"},
        ) from exc
    except AuthSessionStorageError as exc:
        raise _deletion_unavailable() from exc

    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=auth_service.cookie_secure,
        samesite="strict",
    )


def _deletion_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="anonymous account deletion unavailable",
    )
