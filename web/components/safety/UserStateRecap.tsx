import Link from "next/link";
import type { UserState } from "@/lib/api/contracts";
import { USER_STATE_OPTIONS } from "@/lib/format/risk";

/**
 * 사용자가 이미 무엇을 했는지 되짚어 준다.
 *
 * 이 단계가 있어야 다음 섹션의 행동 목록이 "일반론"이 아니라
 * "지금 내 상황에서 할 일"로 읽힌다.
 */
export function UserStateRecap({
  state,
  summary,
}: {
  state: UserState;
  summary: string;
}) {
  const option = USER_STATE_OPTIONS.find((item) => item.value === state);

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="text-body text-foreground">{summary}</p>

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-caption text-muted-foreground">
          선택한 상황: {option?.label ?? state}
        </span>
        <Link
          href="/check"
          className="text-caption font-medium text-primary underline underline-offset-2"
        >
          다시 선택하기
        </Link>
      </div>
    </div>
  );
}
