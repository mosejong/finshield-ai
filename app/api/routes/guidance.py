from fastapi import APIRouter

from app.schemas.wealth_guidance import WealthGuidanceResponse
from app.services.wealth_guidance import get_wealth_guidance


router = APIRouter(prefix="/guidance", tags=["guidance"])


@router.get("/wealth", response_model=WealthGuidanceResponse)
def wealth_guidance() -> WealthGuidanceResponse:
    return get_wealth_guidance()
