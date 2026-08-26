import { describe, expect, it } from "vitest";

import { toExplanation } from "@/lib/api/explanation";

/**
 * 설명 응답을 화면 상태로 옮기는 부분만 본다.
 *
 * 여기서 지키려는 것은 하나다 - **서로 다른 세 가지 '문장이 없다' 를 섞지
 * 않는다.**
 *
 *   off        설명 계층을 켜지 않은 배포다
 *   not_asked  근거가 없어 백엔드가 모델을 부르지 않았다
 *   failed     불렀는데 문장을 받지 못했다
 *
 * 섞으면 세 경우 모두 "설명을 불러오지 못했습니다" 가 뜬다. 가운데 줄은 실측
 * 164건 중 61건이고, 그 61건에서는 **아무것도 실패하지 않았다.**
 */

describe("toExplanation", () => {
  it("계층이 꺼져 있으면 off 다", () => {
    expect(toExplanation({ available: false, explanation: null, model: null })).toEqual({
      status: "off",
      text: null,
      model: null,
    });
  });

  it("물어봤는데 문장이 없으면 failed 다", () => {
    expect(
      toExplanation({ available: true, asked: true, explanation: null, model: null }),
    ).toEqual({
      status: "failed",
      text: null,
      model: null,
    });
  });

  it("근거가 없어 안 물어본 것은 failed 가 아니다", () => {
    // 위험 신호도 권고 행동도 공식 근거도 없는 판정에서는 백엔드가 모델을 부르지
    // 않는다. 실패로 옮기면 화면이 사과를 하는데, 사과할 일이 없다 - 사용자가 읽을
    // 문장은 이미 결정론 요약이 채우고 있다.
    expect(
      toExplanation({ available: true, asked: false, explanation: null, model: null }),
    ).toEqual({
      status: "not_asked",
      text: null,
      model: null,
    });
  });

  it("asked 가 없는 옛 응답은 물어본 것으로 읽는다", () => {
    // 이 필드가 생기기 전의 백엔드는 언제나 물어봤다. 배포 순서가 어긋난 잠깐
    // 동안 없던 상태가 생기지 않게 한다.
    expect(toExplanation({ available: true, explanation: null }).status).toBe("failed");
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
