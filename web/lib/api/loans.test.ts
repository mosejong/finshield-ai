import { afterEach, describe, expect, it, vi } from "vitest";
import {
  compareLoanScenarios,
  simulateLoanScenario,
} from "@/lib/api/loans";

const RESPONSE = {
  principal: "12000000.00",
  annual_interest_rate: "5.2",
  months: 36,
  repayment_type: "equal_principal_and_interest",
  monthly_payment: "360631.51",
  schedule: [
    {
      month: 1,
      principal_payment: "308631.51",
      interest_payment: "52000.00",
      payment: "360631.51",
      remaining_principal: "11691368.49",
    },
  ],
  total_repayment: "12982734.36",
  total_interest: "982734.36",
  assumptions: ["fees are excluded"],
};

const INPUT = {
  principal: 12_000_000,
  annualInterestRate: 5.2,
  months: 36,
  repaymentType: "equal_principal_and_interest" as const,
};

afterEach(() => vi.unstubAllGlobals());

describe("loan simulation API", () => {
  it("백엔드 계약 필드만 전송하고 응답 금액 문자열을 유지한다", async () => {
    const fetchMock = vi.fn().mockImplementation(async () =>
      new Response(JSON.stringify(RESPONSE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await simulateLoanScenario(INPUT);

    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({
      principal: "12000000.00",
      annual_interest_rate: "5.2000",
      months: 36,
      repayment_type: "equal_principal_and_interest",
    });
    expect(result.total_interest).toBe("982734.36");
  });

  it("현재 조건과 바꾼 조건을 각각 백엔드에 계산 요청한다", async () => {
    const fetchMock = vi.fn().mockImplementation(async () =>
      new Response(JSON.stringify(RESPONSE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await compareLoanScenarios(INPUT, { ...INPUT, annualInterestRate: 3.9 });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const secondBody = JSON.parse(fetchMock.mock.calls[1][1].body as string);
    expect(secondBody.annual_interest_rate).toBe("3.9000");
  });

  it("실패를 계산 결과로 바꾸지 않는다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("", { status: 502 })),
    );

    await expect(simulateLoanScenario(INPUT)).rejects.toThrow(
      "대출 상환 결과를 계산하지 못했습니다",
    );
  });

  it("백엔드가 받지 못하는 금리 소수 자릿수를 요청 전에 막는다", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    // 백엔드 LoanSimulationRequest 는 decimal_places=4 라 5자리는 422 가 된다.
    await expect(
      simulateLoanScenario({ ...INPUT, annualInterestRate: 3.12345 }),
    ).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("부동소수점 표기가 백엔드 자릿수 제한을 넘기지 않는다", async () => {
    const fetchMock = vi.fn().mockImplementation(async () =>
      new Response(JSON.stringify(RESPONSE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await simulateLoanScenario({ ...INPUT, annualInterestRate: 0.1 + 0.2 });

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.annual_interest_rate).toBe("0.3000");
    expect(body.annual_interest_rate.split(".")[1].length).toBeLessThanOrEqual(4);
  });
});
