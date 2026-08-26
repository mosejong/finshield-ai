import { Loader2 } from "lucide-react";
import type { Explanation } from "@/lib/api/contracts";

/**
 * 왜 위험한지. 단정하지 않고 "정상 절차와 무엇이 다른가"로 설명한다.
 *
 * 문단이 두 종류다.
 *
 * `paragraphs` 는 결정론 엔진이 만든 요약이다. 규칙에서 바로 나오므로 즉시
 * 그려지고, 이 화면에서 근거의 자격을 갖는 쪽은 이쪽이다.
 *
 * `explanation` 은 그 판정을 모델이 풀어 쓴 문장이다. 8초쯤 걸려 뒤늦게
 * 도착하고, 근거에 없는 연락처·URL 이 섞이면 백엔드 검증기가 통째로 버린다.
 * 없어도 이 블록은 성립해야 한다 - 그래서 아래쪽에 덧붙이는 자리로 두고,
 * 위쪽 요약을 대체하지 않는다.
 */
export function WhyRiskyPanel({
  paragraphs,
  explanation,
}: {
  paragraphs: string[];
  explanation?: Explanation | null;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4">
      {paragraphs.map((paragraph, index) => (
        <p key={index} className="text-body text-foreground">
          {paragraph}
        </p>
      ))}

      {explanation === undefined ? null : (
        <ExplanationBlock explanation={explanation} />
      )}
    </div>
  );
}

/**
 * 두 경우에 아무것도 그리지 않는다.
 *
 * `off` - 설명 계층이 꺼진 배포다. "설명 없음" 을 보여주는 것은 사용자에게 의미가
 * 없다.
 *
 * `not_asked` - 계층은 켜져 있지만 이 판정에 옮겨 쓸 위험 신호도 권고 행동도 공식
 * 근거도 없어서 백엔드가 모델을 부르지 않았다. 이때 "쉬운 말로 다시 설명하면" 이라는
 * 제목만 남기고 그 아래를 비우면 뭔가 실패한 것처럼 보이는데, 실패한 것이 없다.
 * 위쪽 `paragraphs` 가 이미 "명시적인 위험 신호가 확인되지 않았습니다" 를 말하고
 * 있으므로 여기서 덧붙일 문장도 없다.
 *
 * 두 상태를 하나로 합치지 않는 것은 계약 쪽 이야기다. 화면에서 같은 모양이라고
 * 해서 같은 일이 아니고, 나중에 한쪽만 다르게 그리게 되는 날 합쳐 둔 것을 다시
 * 갈라내야 한다.
 */
function ExplanationBlock({ explanation }: { explanation: Explanation | null }) {
  if (explanation?.status === "off") return null;
  if (explanation?.status === "not_asked") return null;

  return (
    <div className="mt-1 border-t border-border pt-3">
      <p className="text-caption font-medium text-muted-foreground">
        쉬운 말로 다시 설명하면
      </p>

      {explanation === null ? (
        <p
          role="status"
          className="mt-2 flex items-center gap-2 text-body text-muted-foreground"
        >
          <Loader2 aria-hidden className="size-4 shrink-0 animate-spin" />
          쉬운 말로 옮기는 중입니다…
        </p>
      ) : null}

      {explanation?.status === "failed" ? (
        <p className="mt-2 text-body text-muted-foreground">
          설명을 불러오지 못했습니다. 위에 적힌 내용이 판단 근거이고, 아래 행동은
          그대로 하시면 됩니다.
        </p>
      ) : null}

      {explanation?.status === "ready" && explanation.text ? (
        <>
          <p className="mt-2 whitespace-pre-line text-body text-foreground">
            {explanation.text}
          </p>
          {explanation.model ? (
            <p className="mt-2 text-caption text-muted-foreground">
              {explanation.model} 이(가) 위 판단 근거만 보고 쓴 문장입니다. 위험
              수준과 행동은 이 문장이 아니라 규칙 엔진이 정합니다.
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
