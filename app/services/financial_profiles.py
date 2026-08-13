from uuid import UUID

from app.repositories.financial_profiles import FinancialProfileRepository
from app.schemas.financial_profile import FinancialProfile, FinancialProfileResource
from app.schemas.profile_metrics import ProfileMetricsResponse
from app.services.profile_metrics import build_profile_metrics


class FinancialProfileService:
    def __init__(self, repository: FinancialProfileRepository) -> None:
        self._repository = repository

    def verify_storage(self) -> None:
        self._repository.verify()

    def create(self, profile: FinancialProfile) -> FinancialProfileResource:
        return self._repository.create(profile)

    def get(self, profile_id: UUID) -> FinancialProfileResource:
        return self._repository.get(profile_id)

    def replace(
        self, profile_id: UUID, profile: FinancialProfile
    ) -> FinancialProfileResource:
        return self._repository.replace(profile_id, profile)

    def delete(self, profile_id: UUID) -> None:
        self._repository.delete(profile_id)

    def metrics(self, profile_id: UUID) -> ProfileMetricsResponse:
        return build_profile_metrics(self._repository.get(profile_id))
