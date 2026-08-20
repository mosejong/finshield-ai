import { describe, expect, it } from "vitest";
import {
  DEPOSIT_CHECK_OPTIONS,
  LEASE_STAGE_OPTIONS,
  isBlankAmount,
  manwonToKrw,
  ratioBandLabel,
} from "@/lib/format/housing";
import {
  DepositCheckSchema,
  LeaseStageSchema,
  MAX_KRW,
} from "@/lib/api/contracts";


describe("manwonToKrw", () => {
  it("만원을 원으로 바꾼다", () => {
    expect(manwonToKrw("20000")).toBe(200_000_000);
  });

  it("빈 칸은 0 이 아니라 null 이다", () => {
    /*
      "모른다" 를 0 으로 보내면 백엔드가 unknown 을 돌려주지 못하고 실제보다
      낮은 비율을 계산한다. 등기부를 아직 안 본 사람이 가장 안심되는 숫자를
      받게 되는데, 정확히 반대로 가야 한다.
    */
    expect(manwonToKrw("")).toBeNull();
    expect(manwonToKrw("   ")).toBeNull();
  });

  it("0 은 0 원으로 그대로 보낸다", () => {
    // 선순위 채권최고액 0원(근저당 없음)은 확인한 사실이지 모르는 값이 아니다.
    expect(manwonToKrw("0")).toBe(0);
  });

  it("숫자가 아닌 입력은 값으로 만들지 않는다", () => {
    expect(manwonToKrw("2억")).toBeNull();
    expect(manwonToKrw("-100")).toBeNull();
    expect(manwonToKrw("1.5")).toBeNull();
  });

  it("백엔드 상한을 넘는 값은 보내지 않는다", () => {
    expect(manwonToKrw(String(MAX_KRW))).toBeNull();
  });
});


describe("isBlankAmount", () => {
  it("공백만 있는 입력도 빈 칸으로 본다", () => {
    expect(isBlankAmount("  ")).toBe(true);
    expect(isBlankAmount("0")).toBe(false);
  });
});


describe("선택지 표", () => {
  it("모든 계약 단계를 빠짐없이 고를 수 있다", () => {
    const offered = LEASE_STAGE_OPTIONS.map((option) => option.value);

    expect(new Set(offered)).toEqual(new Set(LeaseStageSchema.options));
    expect(offered).toHaveLength(LeaseStageSchema.options.length);
  });

  it("모든 확인 항목을 빠짐없이 고를 수 있다", () => {
    const offered = DEPOSIT_CHECK_OPTIONS.map((option) => option.value);

    expect(new Set(offered)).toEqual(new Set(DepositCheckSchema.options));
    expect(offered).toHaveLength(DepositCheckSchema.options.length);
  });

  it("단계 선택지는 되돌리기 어려워지는 순서대로 놓는다", () => {
    expect(LEASE_STAGE_OPTIONS.map((option) => option.value)).toEqual([
      "before_contract",
      "contract_signed",
      "balance_paid",
      "moved_in",
      "lease_ending",
      "deposit_unreturned",
    ]);
  });
});


describe("ratioBandLabel", () => {
  it("어떤 구간도 '안전' 이라고 말하지 않는다", () => {
    /*
      부채비율이 낮다는 것과 그 계약이 안전하다는 것은 다른 말이다.
      뒤쪽은 이 서비스가 할 수 없는 말이다.
    */
    const labels = (["unknown", "low", "elevated", "high"] as const).map(
      ratioBandLabel,
    );

    for (const label of labels) {
      expect(label).not.toContain("안전");
    }
  });

  it("계산하지 못한 상태를 낮음으로 읽히게 하지 않는다", () => {
    expect(ratioBandLabel("unknown")).toBe("확인 전");
  });
});
