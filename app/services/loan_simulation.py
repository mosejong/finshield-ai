from app.domain.finance.loan_calculator import simulate_loan
from app.schemas.loan import (
    LoanSimulationRequest,
    LoanSimulationResponse,
    PaymentScheduleItem,
)


def simulate_loan_request(request: LoanSimulationRequest) -> LoanSimulationResponse:
    result = simulate_loan(
        principal=request.principal,
        annual_interest_rate=request.annual_interest_rate,
        months=request.months,
        repayment_type=request.repayment_type,
    )

    return LoanSimulationResponse(
        principal=result.principal,
        annual_interest_rate=result.annual_interest_rate,
        months=result.months,
        repayment_type=result.repayment_type,
        monthly_payment=result.monthly_payment,
        schedule=[
            PaymentScheduleItem(
                month=item.month,
                principal_payment=item.principal_payment,
                interest_payment=item.interest_payment,
                payment=item.payment,
                remaining_principal=item.remaining_principal,
            )
            for item in result.schedule
        ],
        total_repayment=result.total_repayment,
        total_interest=result.total_interest,
        assumptions=list(result.assumptions),
    )
