"use client";

import { useState } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";
import type { UserState } from "@/lib/api/contracts";
import { USER_STATE_OPTIONS } from "@/lib/format/risk";
import { StateSelector } from "@/components/safety/StateSelector";

/**
 * 사용자가 이미 무엇을 했는지 되짚어 준다.
 *
 * 이 단계가 있어야 다음 섹션의 행동 목록이 "일반론"이 아니라
 * "지금 내 상황에서 할 일"로 읽힌다.
 *
 * 그리고 여기서 상황을 바꿀 수 있어야 한다. 사용자는 결과를 읽는 도중에
 * 자기가 무엇을 했는지 다시 떠올린다 - "아 맞다, 링크는 눌렀었다". 그때
 * `/check` 로 돌려보내면 붙여넣은 문자가 사라지고, 대부분은 다시 붙여넣지
 * 않는다. `recheck` 가 있으면 이 자리에서 바로 다시 확인한다.
 *
 * `recheck` 가 없는 경우(예시 결과이거나 새로고침으로 들어와 원문이 없는
 * 경우)에는 종전대로 `/check` 링크를 보여준다. 물어볼 원문이 없는데 다시
 * 확인 버튼을 그려 두면 눌렀을 때 할 수 있는 일이 없다.
 */
export function UserStateRecap({
  state,
  summary,
  recheck,
}: {
  state: UserState;
  summary: string;
  recheck?: {
    pending: boolean;
    error: string | null;
    onSubmit: (next: UserState) => void;
  };
}) {
  const option = USER_STATE_OPTIONS.find((item) => item.value === state);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<UserState>(state);

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="text-body text-foreground">{summary}</p>

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-caption text-muted-foreground">
          선택한 상황: {option?.label ?? state}
        </span>

        {recheck ? (
          <button
            type="button"
            aria-expanded={open}
            aria-controls="state-recheck"
            onClick={() => {
              setDraft(state);
              setOpen((value) => !value);
            }}
            className="min-h-9 text-caption font-medium text-primary underline underline-offset-2"
          >
            {open ? "그대로 두기" : "상황이 달라졌어요"}
          </button>
        ) : (
          <Link
            href="/check"
            className="text-caption font-medium text-primary underline underline-offset-2"
          >
            다시 선택하기
          </Link>
        )}
      </div>

      {recheck && open ? (
        <div id="state-recheck" className="mt-4 border-t border-border pt-4">
          <p className="mb-3 text-caption text-muted-foreground">
            받은 내용은 그대로 두고 상황만 바꿔 다시 확인합니다. 판정과 해야 할
            행동이 함께 바뀝니다.
          </p>

          <StateSelector value={draft} onChange={setDraft} name="recheck-state" />

          {recheck.error ? (
            <p role="alert" className="mt-3 text-caption text-risk-medium">
              {recheck.error}
            </p>
          ) : null}

          <button
            type="button"
            disabled={recheck.pending || draft === state}
            onClick={() => recheck.onSubmit(draft)}
            className="mt-3 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 text-body font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {recheck.pending ? (
              <>
                <Loader2 aria-hidden className="size-4 animate-spin" />
                다시 확인하는 중…
              </>
            ) : (
              "이 상황으로 다시 확인"
            )}
          </button>
        </div>
      ) : null}
    </div>
  );
}
