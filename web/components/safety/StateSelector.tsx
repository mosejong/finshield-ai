"use client";

import type { UserState } from "@/lib/api/contracts";
import { USER_STATE_OPTIONS } from "@/lib/format/risk";
import { cn } from "@/lib/utils";

/**
 * 사용자가 이미 취한 행동 선택.
 *
 * 선택지 문구는 사용자를 탓하지 않는 평서문으로 쓴다.
 * "당했나요?" 가 아니라 "무엇을 하셨나요?" 다.
 */
export function StateSelector({
  value,
  onChange,
  name = "user-state",
}: {
  value: UserState;
  onChange: (value: UserState) => void;
  name?: string;
}) {
  return (
    <div role="radiogroup" aria-label="이미 하신 행동" className="flex flex-col gap-2">
      {USER_STATE_OPTIONS.map((option) => {
        const selected = option.value === value;

        return (
          <label
            key={option.value}
            className={cn(
              "flex min-h-14 cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors",
              selected
                ? "border-primary bg-secondary"
                : "border-border bg-card hover:bg-secondary",
            )}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={selected}
              onChange={() => onChange(option.value)}
              className="mt-1 size-4 shrink-0 accent-[var(--primary)]"
            />
            <span className="min-w-0 flex-1">
              <span className="block text-body font-medium text-foreground">
                {option.label}
              </span>
              <span className="mt-0.5 block text-caption text-muted-foreground">
                {option.description}
              </span>
            </span>
          </label>
        );
      })}
    </div>
  );
}
