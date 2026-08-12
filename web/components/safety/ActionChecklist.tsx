"use client";

import { useState } from "react";
import { Check, Phone } from "lucide-react";
import type { Action } from "@/lib/api/contracts";
import { actionKindLabel } from "@/lib/format/risk";
import { cn } from "@/lib/utils";

/**
 * 지금 해야 할 행동.
 *
 * 순서: 지금 바로 → 오늘 안에 → 하지 마세요.
 * 정렬은 서비스 레이어가 준 배열 순서를 그대로 따르되, 종류별로 묶어서 보여준다.
 * 체크 상태는 화면 안에서만 쓰는 진행 표시이며 저장하지 않는다.
 */

const KIND_ORDER: Array<Action["kind"]> = ["immediate", "soon", "avoid"];

const KIND_STYLE: Record<Action["kind"], string> = {
  immediate: "text-risk-high",
  soon: "text-primary",
  avoid: "text-risk-medium",
};

export function ActionChecklist({ actions }: { actions: Action[] }) {
  const [done, setDone] = useState<ReadonlySet<string>>(new Set());

  function toggle(id: string) {
    setDone((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const groups = KIND_ORDER.map((kind) => ({
    kind,
    items: actions.filter((action) => action.kind === kind),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="flex flex-col gap-4">
      {groups.map((group) => (
        <div key={group.kind}>
          <p
            className={cn(
              "mb-2 text-caption font-semibold",
              KIND_STYLE[group.kind],
            )}
          >
            {actionKindLabel(group.kind)}
          </p>

          <ul className="flex flex-col gap-2">
            {group.items.map((action) => {
              const checked = done.has(action.id);

              return (
                <li
                  key={action.id}
                  className={cn(
                    "rounded-lg border bg-card p-3 transition-colors",
                    checked ? "border-safe-border bg-safe-bg" : "border-border",
                  )}
                >
                  <div className="flex items-start gap-3">
                    <button
                      type="button"
                      onClick={() => toggle(action.id)}
                      aria-pressed={checked}
                      aria-label={
                        checked ? "완료 취소" : `완료 표시: ${action.title}`
                      }
                      className={cn(
                        "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md border transition-colors",
                        checked
                          ? "border-safe bg-safe text-white"
                          : "border-input bg-background",
                      )}
                    >
                      {checked ? <Check aria-hidden className="size-4" /> : null}
                    </button>

                    <div className="min-w-0 flex-1">
                      <p
                        className={cn(
                          "text-body font-medium",
                          checked
                            ? "text-muted-foreground line-through"
                            : "text-foreground",
                        )}
                      >
                        {action.title}
                      </p>

                      {action.detail ? (
                        <p className="mt-1 text-caption text-muted-foreground">
                          {action.detail}
                        </p>
                      ) : null}

                      {action.contactPhone ? (
                        <a
                          href={`tel:${action.contactPhone}`}
                          className="mt-2 inline-flex min-h-9 items-center gap-1.5 rounded-md border border-border px-3 text-caption font-medium text-primary"
                        >
                          <Phone aria-hidden className="size-3.5" />
                          {action.contactLabel ?? action.contactPhone}
                        </a>
                      ) : null}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
