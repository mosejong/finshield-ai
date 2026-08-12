from fastapi import APIRouter

from app.schemas.loan import LoanSimulationRequest, LoanSimulationResponse
from app.services.loan_simulation import simulate_loan_request


router = APIRouter(prefix="/loans", tags=["loans"])


@router.post("/simulate", response_model=LoanSimulationResponse)
def simulate(request: LoanSimulationRequest) -> LoanSimulationResponse:
    return simulate_loan_request(request)
