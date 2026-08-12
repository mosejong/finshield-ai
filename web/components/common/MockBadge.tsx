import { cn } from "@/lib/utils";
import type { SourceKind } from "@/lib/api/contracts";

/**
 * 백엔드가 아직 제공하지 않아 임시 데이터로 채운 자리라는 표시.
 *
 * 이 배지는 장식이 아니라 정직성 장치다. 사용자가 화면의 어느 부분이
 * 실제 분석이고 어느 부분이 아직 준비 중인지 구분할 수 있어야 한다.
 * (docs/08-ai-security-alignment.md — 응답에 근거와 불확실성을 표시한다)
 */
export function MockBadge({
  source,
  className,
  label = "준비 중",
}: {
  source: SourceKind;
  className?: string;
  label?: string;
}) {
  if (source === "live") return null;

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-sm border border-border bg-secondary px-1.5 py-0.5 text-[0.6875rem] leading-none font-medium text-muted-foreground",
        className,
      )}
      title="백엔드 연동 전이라 임시로 채운 내용입니다."
    >
      {label}
    </span>
  );
}
