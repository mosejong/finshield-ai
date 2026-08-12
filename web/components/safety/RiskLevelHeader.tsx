import type { RiskLevel, SourceKind, UserState } from "@/lib/api/contracts";
import { isRecoveryState, riskStrengthLabel, riskStyle } from "@/lib/format/risk";
import { MockBadge } from "@/components/common/MockBadge";

/**
 * 결과 화면 최상단.
 *
 * 숫자 점수를 여기에 넣지 않는다. 사용자가 가장 먼저 읽어야 하는 것은
 * "지금 무엇을 해야 하는가"를 담은 한 문장이다. 점수는 AnalysisDetails 안에 접어 둔다.
 *
 * 등급 문구를 "메시지 위험 신호"로 한정하는 이유: 백엔드는 붙여넣은 문구만
 * 분석한다. 사용자가 이미 계좌를 넘겼는지는 등급에 반영되어 있지 않다.
 * 그걸 "위험 수준 낮음"이라고 적으면 상황 전체가 안전하다는 뜻으로 읽힌다.
 *
 * 위험색은 좌측 바와 텍스트에만 쓴다. 붉은 배경으로 화면을 덮지 않는다.
 */
export function RiskLevelHeader({
  level,
  headline,
  state,
  source,
}: {
  level: RiskLevel;
  headline: string;
  state: UserState;
  source: SourceKind;
}) {
  const style = riskStyle(level);

  // 이미 넘어간 것이 있는데 초록 tint 로 안심시키지 않는다. 등급 자체는 바꾸지 않는다.
  const softened = level === "low" && isRecoveryState(state);

  return (
    <div
      className={`relative overflow-hidden rounded-lg border p-4 pl-5 ${
        softened ? "border-border bg-card" : style.container
      }`}
    >
      <span
        aria-hidden
        className={`absolute inset-y-0 left-0 w-1 ${
          softened ? "bg-muted-foreground" : style.bar
        }`}
      />

      <div className="flex items-center gap-1.5">
        <span
          className={`text-caption font-semibold ${
            softened ? "text-muted-foreground" : style.text
          }`}
        >
          메시지 위험 신호 {riskStrengthLabel(level)}
        </span>
        <MockBadge source={source} />
      </div>

      <p className="mt-1 text-display text-foreground">{headline}</p>

      {softened ? (
        <p className="mt-2 text-caption text-muted-foreground">
          이 등급은 붙여넣은 문구만 본 결과입니다. 이미 넘어간 것이 있다면 문구와
          상관없이 아래 조치를 먼저 하세요.
        </p>
      ) : null}
    </div>
  );
}
