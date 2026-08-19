import { describe, expect, it } from "vitest";

import { toExplanation } from "@/lib/api/explanation";

/**
 * 설명 응답을 화면 상태로 옮기는 부분만 본다.
 *
 * 여기서 지키려는 것은 하나다 - **꺼진 것과 실패한 것을 섞지 않는다.** 둘을
 * 합치면 설명 계층을 켜지 않은 배포에서 사용자가 매번 "설명을 불러오지
 * 못했습니다" 를 보게 되고, 반대로 켜 놓고 실패한 것은 조용히 사라진다.
 */

describe("toExplanation", () => {
  it("계층이 꺼져 있으면 off 다", () => {
    expect(toExplanation({ available: false, explanation: null, model: null })).toEqual({
      status: "off",
      text: null,
      model: null,
    });
  });

  it("켜져 있는데 문장이 없으면 failed 다", () => {
    expect(toExplanation({ available: true, explanation: null, model: null })).toEqual({
      status: "failed",
      text: null,
      model: null,
    });
  });

  it("문장이 오면 답한 모델까지 함께 남긴다", () => {
    // 주 모델이 막히면 백엔드가 대체 모델로 넘어간다. 화면에 표기되는 이름은
    // 설정된 모델이 아니라 **실제로 답한 모델**이어야 한다.
    expect(
      toExplanation({
        available: true,
        explanation: "정상 절차에 없는 요구입니다.",
        model: "gemini-3.1-flash-lite",
      }),
    ).toEqual({
      status: "ready",
      text: "정상 절차에 없는 요구입니다.",
      model: "gemini-3.1-flash-lite",
    });
  });

  it("model 이 빠진 응답도 받아들인다", () => {
    // 백엔드는 항상 채워 보내지만, 이 값이 없다고 설명을 버릴 이유는 없다.
    const explanation = toExplanation({
      available: true,
      explanation: "정상 절차에 없는 요구입니다.",
    });
    expect(explanation.status).toBe("ready");
    expect(explanation.model).toBeNull();
  });

  it("빈 문자열은 문장이 아니다", () => {
    expect(toExplanation({ available: true, explanation: "", model: "x" }).status).toBe(
      "failed",
    );
  });

  it("형식이 다르면 통과시키지 않는다", () => {
    // 프록시가 다른 경로의 응답을 흘려보내는 식의 사고를 여기서 막는다.
    expect(() => toExplanation({ risk_level: "low" })).toThrow();
  });
});
