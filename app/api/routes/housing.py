from fastapi import APIRouter

from app.schemas.housing import DepositRiskRequest, DepositRiskResponse
from app.services.housing_deposit import check_deposit_risk


router = APIRouter(prefix="/housing", tags=["housing"])


@router.post("/deposit-risk", response_model=DepositRiskResponse)
def deposit_risk(request: DepositRiskRequest) -> DepositRiskResponse:
    """전세보증금 위험 점검.

    프로필이나 세션을 요구하지 않는다. 계약을 앞둔 사람에게 회원가입을 먼저
    시키면 그 자리에서 이탈한다. 입력값은 저장하지 않고 응답만 만든다 —
    보증금·주택가격은 저장할 이유가 없는 민감한 값이다.
    """
    return check_deposit_risk(request)
