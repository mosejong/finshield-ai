from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.repositories.financial_profiles import (
    FinancialProfileCapacityError,
    FinancialProfileNotFoundError,
    InMemoryFinancialProfileRepository,
)
from app.schemas.financial_profile import FinancialProfile, FinancialProfileResource
from app.schemas.profile_metrics import ProfileMetricsResponse
from app.services.financial_profiles import FinancialProfileService


router = APIRouter(prefix="/profiles", tags=["profiles"])

_repository = InMemoryFinancialProfileRepository()
_service = FinancialProfileService(_repository)


def get_financial_profile_service() -> FinancialProfileService:
    return _service


ProfileServiceDependency = Annotated[
    FinancialProfileService, Depends(get_financial_profile_service)
]


@router.post(
    "",
    response_model=FinancialProfileResource,
    status_code=status.HTTP_201_CREATED,
)
def create_profile(
    profile: FinancialProfile,
    service: ProfileServiceDependency,
) -> FinancialProfileResource:
    try:
        return service.create(profile)
    except FinancialProfileCapacityError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="profile storage capacity reached",
        ) from exc


@router.get("/{profile_id}", response_model=FinancialProfileResource)
def get_profile(
    profile_id: UUID,
    service: ProfileServiceDependency,
) -> FinancialProfileResource:
    try:
        return service.get(profile_id)
    except FinancialProfileNotFoundError as exc:
        raise _not_found() from exc


@router.get("/{profile_id}/metrics", response_model=ProfileMetricsResponse)
def get_profile_metrics(
    profile_id: UUID,
    service: ProfileServiceDependency,
) -> ProfileMetricsResponse:
    try:
        return service.metrics(profile_id)
    except FinancialProfileNotFoundError as exc:
        raise _not_found() from exc


@router.put("/{profile_id}", response_model=FinancialProfileResource)
def replace_profile(
    profile_id: UUID,
    profile: FinancialProfile,
    service: ProfileServiceDependency,
) -> FinancialProfileResource:
    try:
        return service.replace(profile_id, profile)
    except FinancialProfileNotFoundError as exc:
        raise _not_found() from exc


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: UUID,
    service: ProfileServiceDependency,
) -> Response:
    try:
        service.delete(profile_id)
    except FinancialProfileNotFoundError as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="financial profile not found",
    )
