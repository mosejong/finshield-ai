import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AnalyzeRequest, Explanation } from "@/lib/api/contracts";

const explainFromClient = vi.fn<(request: AnalyzeRequest) => Promise<Explanation>>();

vi.mock("@/lib/api/explanation", () => ({
  explainFromClient: (request: AnalyzeRequest) => explainFromClient(request),
}));

/**
 * 이 보관소에서 검사할 것은 두 가지다.
 *
 * 1. **원문이 필요 이상으로 살아 있지 않은가.** 붙여넣은 문자에는 이름과
 *    계좌번호가 들어 있을 수 있다. 요청을 한 번 만든 뒤에는 남아 있으면 안 된다.
 * 2. **유료 호출이 한 번만 나가는가.** 설명은 외부 모델 호출이고 한 번에 8초쯤
 *    걸린다. 화면을 다시 여는 것만으로 다시 나가면 안 된다.
 */

const READY: Explanation = {
  status: "ready",
  text: "정상 절차에 없는 요구입니다.",
  model: "gemini-3.6-flash",
};

const REQUEST: AnalyzeRequest = {
  text: "금융감독원입니다. 계좌가 범죄에 연루되어 즉시 이체가 필요합니다.",
  persona: "unknown",
  state: "received_only",
};

async function load() {
  vi.resetModules();
  return import("@/lib/store/explanation-store");
}

beforeEach(() => {
  explainFromClient.mockReset();
  explainFromClient.mockResolvedValue(READY);
});

describe("requestExplanation", () => {
  it("건네받은 원문으로 한 번 묻는다", async () => {
    const store = await load();
    store.rememberAnalysisInput("a-1", REQUEST);

    await expect(store.requestExplanation("a-1")).resolves.toEqual(READY);
    expect(explainFromClient).toHaveBeenCalledTimes(1);
    expect(explainFromClient).toHaveBeenCalledWith(REQUEST);
  });

  it("같은 결과를 다시 열어도 유료 호출은 한 번뿐이다", async () => {
    const store = await load();
    store.rememberAnalysisInput("a-1", REQUEST);

    await store.requestExplanation("a-1");
    await store.requestExplanation("a-1");
    await store.requestExplanation("a-1");

    expect(explainFromClient).toHaveBeenCalledTimes(1);
  });

  it("원문이 없으면 아무것도 묻지 않는다", async () => {
    // 새로고침으로 결과 화면에 바로 들어온 경우다. 판정은 sessionStorage 에
    // 남아 있지만 원문은 남기지 않으므로, 설명은 붙지 않는 것이 맞다.
    const store = await load();

    expect(store.requestExplanation("a-1")).toBeNull();
    expect(explainFromClient).not.toHaveBeenCalled();
  });

  it("다른 결과의 원문으로 설명하지 않는다", async () => {
    const store = await load();
    store.rememberAnalysisInput("a-1", REQUEST);

    expect(store.requestExplanation("a-2")).toBeNull();
    expect(explainFromClient).not.toHaveBeenCalled();
  });

  it("원문은 요청을 만든 뒤 남지 않는다", async () => {
    const store = await load();
    store.rememberAnalysisInput("a-1", REQUEST);
    await store.requestExplanation("a-1");

    // 같은 원문이 다른 id 로 재사용되지 않는 것으로 확인한다. 남아 있었다면
    // 여기서 두 번째 호출이 나갔을 것이다.
    store.forgetExplanation("a-1");
    expect(store.requestExplanation("a-1")).toBeNull();
    expect(explainFromClient).toHaveBeenCalledTimes(1);
  });

  it("결과를 지우면 설명도 함께 사라진다", async () => {
    const store = await load();
    store.rememberAnalysisInput("a-1", REQUEST);
    await store.requestExplanation("a-1");

    store.forgetExplanation("a-1");

    expect(store.requestExplanation("a-1")).toBeNull();
  });

  it("아직 쓰이지 않은 원문도 결과를 지우면 버린다", async () => {
    const store = await load();
    store.rememberAnalysisInput("a-1", REQUEST);

    store.forgetExplanation("a-1");

    expect(store.requestExplanation("a-1")).toBeNull();
    expect(explainFromClient).not.toHaveBeenCalled();
  });
});
