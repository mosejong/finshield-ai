from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
def readiness() -> dict[str, str]:
    from app.api.routes.auth import verify_auth_session_storage
    from app.api.routes.profiles import verify_financial_profile_storage
    from app.repositories.auth_sessions import AuthSessionStorageError
    from app.repositories.financial_profiles import FinancialProfileStorageError

    try:
        verify_auth_session_storage()
        verify_financial_profile_storage()
    except (AuthSessionStorageError, FinancialProfileStorageError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="storage unavailable",
        ) from exc
    return {"status": "ready"}
