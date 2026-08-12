import type { RiskLevel, SourceKind } from "@/lib/api/contracts";
import { riskStrengthLabel, riskStyle } from "@/lib/format/risk";
import { MockBadge } from "@/components/common/MockBadge";

/**
 * 결과 화면 최상단.
 *
 * 숫자 점수를 여기에 넣지 않는다. 사용자가 가장 먼저 읽어야 하는 것은
 * "지금 무엇을 해야 하는가"를 담은 한 문장이다. 점수는 AnalysisDetails 안에 접어 둔다.
 *
 * Scenario Engine의 등급은 문구 신호와 사용자가 선택한 현재 상태를 함께 반영한다.
 *
 * 위험색은 좌측 바와 텍스트에만 쓴다. 붉은 배경으로 화면을 덮지 않는다.
 */
export function RiskLevelHeader({
  level,
  headline,
  source,
}: {
  level: RiskLevel;
  headline: string;
  source: SourceKind;
}) {
  const style = riskStyle(level);

  return (
    <div
      className={`relative overflow-hidden rounded-lg border p-4 pl-5 ${style.container}`}
    >
      <span
        aria-hidden
        className={`absolute inset-y-0 left-0 w-1 ${style.bar}`}
      />

      <div className="flex items-center gap-1.5">
        <span
          className={`text-caption font-semibold ${style.text}`}
        >
          현재 상황 위험도 {riskStrengthLabel(level)}
        </span>
        <MockBadge source={source} />
      </div>

      <p className="mt-1 text-display text-foreground">{headline}</p>
    </div>
  );
}
