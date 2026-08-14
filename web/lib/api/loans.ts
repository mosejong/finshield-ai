import {
  LoanScenarioInputSchema,
  LoanSimulationResponseSchema,
  MAX_INTEREST_RATE_DECIMALS,
  type LoanScenarioInput,
  type LoanSimulationResponse,
} from "@/lib/api/contracts";

export type LoanWhatIfComparison = {
  current: LoanSimulationResponse;
  alternative: LoanSimulationResponse;
};

export async function simulateLoanScenario(
  input: LoanScenarioInput,
): Promise<LoanSimulationResponse> {
  const parsed = LoanScenarioInputSchema.parse(input);
  const response = await fetch("/api/proxy/loans/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      principal: parsed.principal.toFixed(2),
      // 부동소수점 표기가 백엔드의 decimal_places 제한을 넘지 않도록 자릿수를 고정한다.
      annual_interest_rate: parsed.annualInterestRate.toFixed(
        MAX_INTEREST_RATE_DECIMALS,
      ),
      months: parsed.months,
      repayment_type: parsed.repaymentType,
    }),
  });

  if (!response.ok) {
    throw new Error("대출 상환 결과를 계산하지 못했습니다.");
  }

  return LoanSimulationResponseSchema.parse(await response.json());
}

export async function compareLoanScenarios(
  current: LoanScenarioInput,
  alternative: LoanScenarioInput,
): Promise<LoanWhatIfComparison> {
  const [currentResult, alternativeResult] = await Promise.all([
    simulateLoanScenario(current),
    simulateLoanScenario(alternative),
  ]);

  return { current: currentResult, alternative: alternativeResult };
}
