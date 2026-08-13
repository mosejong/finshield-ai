import { cn } from "@/lib/utils";
import type { SourceKind } from "@/lib/api/contracts";

/**
 * 실제 사용자 데이터가 아닌 고정 예시·fallback이라는 표시.
 *
 * 이 배지는 장식이 아니라 정직성 장치다. 사용자가 화면의 어느 부분이
 * live 응답이고 어느 부분이 예시인지 구분할 수 있어야 한다.
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
      title="실제 사용자 데이터가 아닌 고정 예시입니다."
    >
      {label}
    </span>
  );
}
