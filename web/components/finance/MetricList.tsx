import type { DerivedMetric } from "@/lib/api/contracts";
import { cn } from "@/lib/utils";

const TONE_CLASS: Record<DerivedMetric["tone"], string> = {
  positive: "text-safe",
  neutral: "text-foreground",
  caution: "text-risk-medium",
};

/**
 * 파생지표 목록.
 *
 * 값은 서비스 레이어가 계산해서 문자열로 내려준 것을 그대로 표시한다.
 * 여기서 나누거나 곱하지 않는다.
 */
export function MetricList({ metrics }: { metrics: DerivedMetric[] }) {
  return (
    <ul className="flex flex-col gap-3">
      {metrics.map((metric) => (
        <li
          key={metric.key}
          className="rounded-lg border border-border bg-card p-4"
        >
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-body text-muted-foreground">
              {metric.label}
            </span>
            <span
              className={cn("text-title tabular-nums", TONE_CLASS[metric.tone])}
            >
              {metric.display}
            </span>
          </div>

          <p className="mt-1.5 text-caption text-muted-foreground">
            {metric.hint}
          </p>

          {metric.caveat ? (
            <p className="mt-2 border-t border-border pt-2 text-caption text-muted-foreground">
              {metric.caveat}
            </p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
