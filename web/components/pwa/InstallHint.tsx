"use client";

import { useSyncExternalStore } from "react";
import {
  readSession,
  subscribeSession,
  writeSession,
} from "@/lib/store/session-store";

/**
 * "홈 화면에 추가하면 다음엔 공유 버튼으로 바로 올 수 있습니다" 안내.
 *
 * 홈이 아니라 확인 결과 화면에 두는 이유가 두 가지다. 홈은 블록 4개로 고정돼
 * 있고(docs/13), 무엇보다 설치의 값어치는 결과를 한 번 본 뒤에야 와닿는다.
 * 아직 뭘 해주는 앱인지 모르는 사람에게 설치부터 권하면 그냥 배너 하나다.
 *
 * 브라우저가 설치 가능하다고 알려줄 때(`beforeinstallprompt`)만 버튼을 띄운다.
 * 이 이벤트는 iOS Safari 에 없으므로 - Next 문서도 이 이벤트에 의존하지 말라고
 * 적어 두었다 - iOS 에서는 버튼 대신 방법을 글로 알려준다. 둘 다 아니면
 * 아무것도 그리지 않는다. 설치할 수 없는 곳에서 설치를 권하지 않는다.
 */

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

const DISMISSED_KEY = "finshield:install-hint:dismissed";

/*
 * `beforeinstallprompt` 는 보통 React 가 마운트되기 전에 한 번 발생하고 만다.
 * 컴포넌트 안에서 구독하면 이미 지나간 뒤라 영영 못 받는다. 그래서 모듈이
 * 평가될 때 창에 바로 붙여 두고, 컴포넌트는 잡아 둔 값을 구독만 한다.
 */
let capturedPrompt: BeforeInstallPromptEvent | null = null;
const promptListeners = new Set<() => void>();

function notifyPromptChange(): void {
  for (const listener of promptListeners) listener();
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (event) => {
    // 브라우저 기본 배너를 막고, 우리가 문맥에 맞는 자리에서 띄운다.
    event.preventDefault();
    capturedPrompt = event as BeforeInstallPromptEvent;
    notifyPromptChange();
  });
}

function subscribePrompt(listener: () => void): () => void {
  promptListeners.add(listener);
  return () => {
    promptListeners.delete(listener);
  };
}

/** 홈 화면에서 열렸는지. 이미 설치된 사람에게 설치를 권하지 않는다. */
function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    // iOS Safari 는 display-mode 대신 이 속성을 쓴다.
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function isIOS(): boolean {
  return /iPad|iPhone|iPod/.test(navigator.userAgent);
}

export function InstallHint() {
  const prompt = useSyncExternalStore(
    subscribePrompt,
    () => capturedPrompt,
    () => null,
  );

  // 서버 스냅샷을 "숨김"으로 두면 하이드레이션 전에는 아무것도 그리지 않는다.
  // 브라우저 사정(설치 여부·기기)은 그 뒤에야 알 수 있다.
  const hidden = useSyncExternalStore(
    subscribeSession,
    () => readSession(DISMISSED_KEY) === "1" || isStandalone(),
    () => true,
  );

  if (hidden) return null;

  const iOS = isIOS();
  if (!prompt && !iOS) return null;

  function hide() {
    writeSession(DISMISSED_KEY, "1");
  }

  async function install() {
    if (!prompt) return;
    await prompt.prompt();
    // 결과와 무관하게 이 이벤트는 한 번만 쓸 수 있다.
    capturedPrompt = null;
    notifyPromptChange();
    hide();
  }

  return (
    <aside
      aria-labelledby="install-hint-title"
      className="mt-6 rounded-lg border border-border bg-secondary/60 p-4"
    >
      <h2 id="install-hint-title" className="text-body font-semibold text-foreground">
        다음엔 문자 앱에서 바로 보내세요
      </h2>
      <p className="mt-1 text-caption text-muted-foreground">
        홈 화면에 추가해 두면, 의심스러운 문자를 받았을 때 공유 버튼에서 FinShield 를
        골라 곧바로 확인할 수 있습니다. 복사해서 붙여넣는 단계가 사라집니다.
      </p>

      {prompt ? (
        <button
          type="button"
          onClick={install}
          className="mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-md bg-primary px-4 text-body font-semibold text-primary-foreground transition-opacity hover:opacity-90"
        >
          홈 화면에 추가
        </button>
      ) : (
        <p className="mt-3 text-caption text-foreground">
          Safari 아래쪽 공유 버튼을 누르고 <b>홈 화면에 추가</b>를 선택하세요.
        </p>
      )}

      <button
        type="button"
        onClick={hide}
        className="mt-2 min-h-9 text-caption font-medium text-muted-foreground underline underline-offset-2 hover:text-foreground"
      >
        괜찮습니다
      </button>
    </aside>
  );
}
