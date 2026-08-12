import { ChevronDown } from "lucide-react";
import type { AnalysisResult } from "@/lib/api/contracts";
import { MockBadge } from "@/components/common/MockBadge";
import { formatDateTime } from "@/lib/format/risk";

/**
 * 분석 상세 — 기본 접힘.
 *
 * 숫자 점수가 나오는 곳은 화면 전체에서 여기 한 곳뿐이다.
 * 점수를 먼저 보여주면 사용자가 "87점이면 얼마나 위험한가"를 해석하려 애쓰게 되고,
 * 정작 읽어야 할 행동 지시를 지나친다. 그래서 근거를 확인하려는 사람만 펼치게 둔다.
 */
export function AnalysisDetails({ result }: { result: AnalysisResult }) {
  return (
    <details className="group rounded-lg border border-border bg-card">
      <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-body font-medium text-foreground [&::-webkit-details-marker]:hidden">
        분석 상세
        <ChevronDown
          aria-hidden
          className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
        />
      </summary>

      <div className="border-t border-border px-4 py-3">
        <dl className="flex flex-col gap-2 text-caption">
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-muted-foreground">위험 점수</dt>
            <dd className="flex items-center gap-1.5 font-medium text-foreground">
              <span className="tabular-nums">{result.score} / 100</span>
              <MockBadge source={result.scoreSource} label="예시" />
            </dd>
          </div>

          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-muted-foreground">판정 방식</dt>
            <dd className="text-right font-medium text-foreground">
              {result.engine}
            </dd>
          </div>

          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-muted-foreground">분석 시각</dt>
            <dd className="font-medium text-foreground">
              {formatDateTime(result.createdAt)}
            </dd>
          </div>
        </dl>

        {result.signals.length > 0 ? (
          <div className="mt-4">
            <p className="mb-1.5 text-caption text-muted-foreground">
              점수에 반영된 신호
            </p>
            <ul className="flex flex-col gap-1">
              {result.signals.map((signal) => (
                <li
                  key={signal.code}
                  className="flex items-baseline justify-between gap-3 text-caption"
                >
                  <span className="text-foreground">{signal.label}</span>
                  <span className="shrink-0 font-mono text-muted-foreground tabular-nums">
                    {signal.code} +{signal.weight}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <p className="mt-4 text-caption text-muted-foreground">
          점수는 규칙에 걸린 신호의 가중치를 합한 값입니다. 점수가 낮다고 안전이
          보장되지는 않으며, 판단이 서지 않을 때는 해당 기관 공식 번호로 직접
          확인하세요.
        </p>
      </div>
    </details>
  );
}
