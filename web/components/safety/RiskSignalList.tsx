import type { RiskSignal } from "@/lib/api/contracts";
import { MockBadge } from "@/components/common/MockBadge";

/**
 * 감지된 위험 신호.
 *
 * live 신호는 Scenario Engine 응답을 그대로 표시한다. mock 모드에서만
 * 예시 설명이 붙으므로 그 경우에 한해 배지를 표시한다.
 */
export function RiskSignalList({ signals }: { signals: RiskSignal[] }) {
  if (signals.length === 0) {
    return (
      <p className="rounded-lg border border-border bg-card p-4 text-body text-muted-foreground">
        계좌 요구, 인증정보 요구, 자금 전달 요구 같은 위험 신호는 감지되지
        않았습니다.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {signals.map((signal) => (
        <li
          key={signal.code}
          className="rounded-lg border border-border bg-card p-4"
        >
          <div className="flex items-start gap-2.5">
            <span
              aria-hidden
              className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground"
            />
            <div className="min-w-0 flex-1">
              <p className="text-body font-medium text-foreground">
                {signal.label}
              </p>
              {signal.why ? (
                <p className="mt-1 text-caption text-muted-foreground">
                  {signal.why}
                </p>
              ) : null}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function SignalExplanationBadge({ signals }: { signals: RiskSignal[] }) {
  const hasMockExplanation = signals.some(
    (signal) => signal.why && signal.source === "mock",
  );
  return hasMockExplanation ? <MockBadge source="mock" label="예시" /> : null;
}
