import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AnalyzeRequest } from "@/lib/api/contracts";

/**
 * 이 보관소는 `explanation-store` 와 달리 원문을 **더 오래** 들고 있는다.
 * 사용자가 결과를 읽다가 "아 맞다, 링크는 눌렀었다"를 떠올릴 때까지다.
 *
 * 그래서 검사할 것도 그 대가에 맞춘다.
 *
 * 1. **저장소에 쓰지 않는가.** 새로고침으로 살아나면 안 된다.
 * 2. **한 건만 남는가.** 앞의 원문이 뒤의 결과에 붙으면 안 된다.
 * 3. **결과를 지울 때 같이 사라지는가.** 원문이 결과보다 오래 남을 수 없다.
 */

const REQUEST: AnalyzeRequest = {
  text: "금융감독원입니다. 계좌가 범죄에 연루되어 즉시 이체가 필요합니다.",
  persona: "unknown",
  state: "received_only",
};

const OTHER: AnalyzeRequest = {
  text: "택배 주소가 잘못되었습니다. 아래 주소에서 확인해 주세요.",
  persona: "unknown",
  state: "clicked_link",
};

async function load() {
  vi.resetModules();
  return import("@/lib/store/recheck-store");
}

/*
  이 테스트는 node 환경에서 돈다 (`vitest.config.ts`). 브라우저 저장소가 아예
  없으므로, 보관소가 저장소에 손을 대면 그것이 눈에 보이도록 가짜를 하나
  꽂아 두고 `setItem` 이 불렸는지로 확인한다.
*/
const setItem = vi.fn();

function fakeStorage() {
  return { setItem, getItem: () => null, removeItem: vi.fn(), clear: vi.fn(), key: () => null, length: 0 };
}

beforeEach(() => {
  setItem.mockReset();
  vi.stubGlobal("sessionStorage", fakeStorage());
  vi.stubGlobal("localStorage", fakeStorage());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("recheckInputFor", () => {
  it("방금 분석한 결과의 원문을 돌려준다", async () => {
    const store = await load();
    store.rememberRecheckInput("a-1", REQUEST);

    expect(store.recheckInputFor("a-1")).toEqual(REQUEST);
  });

  it("다른 결과의 원문은 돌려주지 않는다", async () => {
    const store = await load();
    store.rememberRecheckInput("a-1", REQUEST);

    // 결과 화면이 이 값을 그대로 다시 보내므로, 여기서 새면 사용자가 A 를 보며
    // 고친 상황이 B 의 문자로 판정된다.
    expect(store.recheckInputFor("a-2")).toBeNull();
  });

  it("새로 분석하면 앞의 원문은 사라진다", async () => {
    const store = await load();
    store.rememberRecheckInput("a-1", REQUEST);
    store.rememberRecheckInput("a-2", OTHER);

    expect(store.recheckInputFor("a-2")).toEqual(OTHER);
    expect(store.recheckInputFor("a-1")).toBeNull();
  });

  it("아무것도 넘겨받지 못했으면 없다", async () => {
    // 새로고침으로 결과 화면에 바로 들어온 경우다. 이때 화면은 다시 확인
    // 버튼 대신 `/check` 링크로 물러난다.
    const store = await load();

    expect(store.recheckInputFor("a-1")).toBeNull();
  });
});

describe("forgetRecheckInput", () => {
  it("결과를 지우면 원문도 사라진다", async () => {
    const store = await load();
    store.rememberRecheckInput("a-1", REQUEST);

    store.forgetRecheckInput("a-1");

    expect(store.recheckInputFor("a-1")).toBeNull();
  });

  it("다른 결과를 지워도 지금 원문은 남는다", async () => {
    const store = await load();
    store.rememberRecheckInput("a-1", REQUEST);

    store.forgetRecheckInput("a-2");

    expect(store.recheckInputFor("a-1")).toEqual(REQUEST);
  });
});

describe("보관 위치", () => {
  it("브라우저 저장소에 쓰지 않는다", async () => {
    const store = await load();
    store.rememberRecheckInput("a-1", REQUEST);

    expect(setItem).not.toHaveBeenCalled();
  });

  it("모듈이 다시 올라오면 남지 않는다", async () => {
    const first = await load();
    first.rememberRecheckInput("a-1", REQUEST);

    // 탭을 새로 여는 것에 해당한다. 메모리 한 칸이므로 빈 상태여야 한다.
    const second = await load();

    expect(second.recheckInputFor("a-1")).toBeNull();
  });
});
