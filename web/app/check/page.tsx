"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import type { UserState } from "@/lib/api/contracts";
import { ANALYZE_TEXT_MAX_LENGTH } from "@/lib/api/contracts";
import { usePendingShare } from "@/lib/share/pending";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { SectionHeading } from "@/components/common/SectionHeading";
import { DisclaimerNote } from "@/components/common/DisclaimerNote";
import { StateSelector } from "@/components/safety/StateSelector";
import { analyzeFromClient } from "@/lib/api/analysis";
import { saveAnalysis } from "@/lib/store/analysis-store";
import { rememberAnalysisInput } from "@/lib/store/explanation-store";
import { useProfileStore } from "@/lib/store/profile-store";

/**
 * 의심 메시지 입력 + 피해 단계 선택.
 *
 * 이 화면은 프로필 없이 동작한다. 의심 문자를 방금 받은 사람에게 온보딩을
 * 먼저 요구하면 이탈한다. 프로필이 있으면 persona 만 함께 보낸다.
 *
 * 위험 판정은 전부 백엔드가 한다. 여기서는 입력을 모아 보내고 결과를 넘길 뿐,
 * 키워드 검사나 점수 계산을 하지 않는다.
 */

const MAX_LENGTH = ANALYZE_TEXT_MAX_LENGTH;

export default function CheckPage() {
  const router = useRouter();

  /**
   * 공유 시트로 들어온 경우 `/check/shared` 가 sessionStorage 에 놓고 넘겨준
   * 내용. 자동으로 분석까지 보내지는 않는다 - 어떤 내용이 넘어왔는지 사용자가
   * 먼저 보고, "이미 하신 행동"을 고를 수 있어야 한다.
   *
   * 편집하기 전까지는 공유된 내용을 그대로 보여주고, 한 글자라도 고치면 그때부터
   * `edited` 가 화면의 값이 된다. 공유 내용을 초기값으로 복사해 넣지 않는 이유는
   * 하이드레이션 이후에 setState 를 한 번 더 돌려야 하기 때문이다.
   */
  const shared = usePendingShare();
  const [edited, setEdited] = useState<string | null>(null);
  const text = edited ?? shared ?? "";

  const [state, setState] = useState<UserState>("received_only");
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<{
    message: string;
    hint?: string;
  } | null>(null);

  // 프로필이 있으면 persona 만 함께 보낸다. 없으면 unknown 으로 그냥 진행한다.
  const persona = useProfileStore().profile?.persona ?? "unknown";

  const trimmed = text.trim();
  const canSubmit = trimmed.length > 0 && trimmed.length <= MAX_LENGTH;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit || pending) return;

    setPending(true);
    setFailure(null);

    const request = { text: trimmed, persona, state };
    const response = await analyzeFromClient(request);

    if (!response.ok) {
      setFailure({ message: response.message, hint: response.hint });
      setPending(false);
      return;
    }

    saveAnalysis(response.result);
    /*
      설명은 결과 화면에서 따로 받아온다. 여기서 기다리면 8초 뒤에야 위험
      수준이 뜬다. 원문은 저장소가 아니라 메모리로만 넘긴다 - 이유는
      `explanation-store.ts` 에 적었다.
    */
    rememberAnalysisInput(response.result.id, request);
    router.push(`/check/result/${response.result.id}`);
  }

  return (
    <AppShell>
      <PageHeader
        title="위험한 금융 연락 확인"
        description="받은 문자나 메신저 내용을 그대로 붙여넣으면, 어떤 부분이 정상 절차와 다른지 알려드립니다."
        backHref="/"
      />

      <form onSubmit={handleSubmit} className="flex flex-col gap-7">
        <section aria-labelledby="check-input">
          <SectionHeading>
            <span id="check-input">받은 내용</span>
          </SectionHeading>

          {shared ? (
            <p
              role="status"
              className="mb-2 rounded-md border border-border bg-secondary/60 px-3 py-2 text-caption text-muted-foreground"
            >
              공유하신 내용을 불러왔습니다. 확인 전에 고치거나 지우셔도 됩니다.
            </p>
          ) : null}

          <label className="flex flex-col gap-1.5">
            <span className="sr-only">받은 메시지 내용</span>
            <textarea
              id="check-message"
              value={text}
              onChange={(event) => setEdited(event.target.value.slice(0, MAX_LENGTH))}
              rows={7}
              aria-describedby="check-message-help check-message-count check-message-privacy"
              placeholder="예) 급여 계좌 등록이 필요합니다. 오늘 안에 체크카드를 아래 주소로 보내주세요."
              className="w-full resize-y rounded-md border border-input bg-background p-3 text-body text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
            />
            <span className="flex items-center justify-between gap-2 text-caption text-muted-foreground">
              <span id="check-message-help">
                링크가 있어도 지우지 말고 그대로 붙여넣으세요. 저희가 그 링크를
                열어보지는 않습니다.
              </span>
              <span
                id="check-message-count"
                className="shrink-0 tabular-nums"
                aria-label={`입력 글자 수 ${text.length.toLocaleString("ko-KR")}자, 최대 ${MAX_LENGTH.toLocaleString("ko-KR")}자`}
              >
                {text.length.toLocaleString("ko-KR")} / {MAX_LENGTH.toLocaleString("ko-KR")}
              </span>
            </span>
          </label>

          <p id="check-message-privacy" className="mt-2 text-caption text-muted-foreground">
            주민등록번호, 계좌 비밀번호, 인증번호는 붙여넣지 마세요. 분석에 필요하지
            않습니다.
          </p>
        </section>

        <section aria-labelledby="check-state">
          <SectionHeading>
            <span id="check-state">이미 하신 행동</span>
          </SectionHeading>
          <p className="mb-3 text-caption text-muted-foreground">
            무엇을 했는지에 따라 지금 해야 할 조치가 달라집니다. 이미 넘어간 것이
            있어도 늦지 않았습니다.
          </p>

          <StateSelector value={state} onChange={setState} />
        </section>

        {failure ? (
          <div
            role="alert"
            className="rounded-lg border border-risk-medium-border bg-risk-medium-bg p-4"
          >
            <p className="text-body font-medium text-risk-medium">
              {failure.message}
            </p>
            {failure.hint ? (
              <p className="mt-1 text-caption text-muted-foreground">
                {failure.hint}
              </p>
            ) : null}
            <p className="mt-2 text-caption text-muted-foreground">
              결과를 확인하지 못했다고 해서 안전하다는 뜻은 아닙니다. 판단이 서지
              않으면 상대가 말한 기관의 공식 대표번호로 직접 확인하세요.
            </p>
          </div>
        ) : null}

        <div className="sticky bottom-[calc(4.5rem+env(safe-area-inset-bottom))] flex flex-col gap-2 border-t border-border bg-background py-3 lg:static lg:border-0 lg:py-0">
          <button
            type="submit"
            disabled={!canSubmit || pending}
            aria-busy={pending}
            className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 text-body font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-45"
          >
            {pending ? (
              <>
                <Loader2 aria-hidden className="size-4 animate-spin" />
                확인하는 중…
              </>
            ) : (
              "확인하기"
            )}
          </button>

          <p className="text-center text-caption text-muted-foreground">
            붙여넣은 내용은 분석에만 쓰이고 저장하지 않습니다.{" "}
            <Link
              href="/check/result/demo"
              className="font-medium text-primary underline underline-offset-2"
            >
              예시 결과 보기
            </Link>
          </p>
        </div>
      </form>

      {/*
        급한 사람의 경로를 막지 않도록 폼 아래에 둔다. 전세 계약 확인은 지금
        문자를 받은 사람이 먼저 눌러야 할 것이 아니다.
      */}
      <section aria-labelledby="check-other" className="mt-10">
        <SectionHeading>
          <span id="check-other">다른 확인</span>
        </SectionHeading>

        <Link
          href="/check/deposit"
          className="flex items-start gap-3 rounded-lg border border-border bg-card p-4 transition-colors hover:bg-secondary"
        >
          <div className="min-w-0 flex-1">
            <p className="text-body font-medium text-foreground">
              전세보증금 위험 점검
            </p>
            <p className="mt-1 text-caption text-muted-foreground">
              계약 단계와 금액을 넣으면 등기부 확인·전입신고·확정일자 중 무엇이
              비어 있는지 짚어드립니다.
            </p>
          </div>
        </Link>
      </section>

      <DisclaimerNote>
        이 확인은 위험 신호를 찾아주는 보조 도구이며 금융·법률 판단을 대신하지
        않습니다. 이미 피해가 발생했다면 경찰(112)과 거래 은행에 먼저 연락하세요.
      </DisclaimerNote>
    </AppShell>
  );
}
