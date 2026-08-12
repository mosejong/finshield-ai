import { ExternalLink, Phone } from "lucide-react";
import type { Evidence } from "@/lib/api/contracts";

/**
 * 공식 근거/출처.
 *
 * 확인되지 않은 항목은 "공식 확인 전"으로 분명히 표시한다.
 * 근거가 없는데 있는 척하지 않는 것이 이 서비스의 전제다.
 * (CLAUDE.md — Official APIs are source of truth, retain provenance)
 */
export function EvidenceList({ items }: { items: Evidence[] }) {
  if (items.length === 0) return null;

  const hasUnverified = items.some((item) => !item.verified);

  return (
    <div className="rounded-lg border border-border bg-secondary/60 p-4">
      {hasUnverified ? (
        <p className="mb-3 text-caption text-muted-foreground">
          아래 창구는 실제로 존재하는 기관이지만, 안내 내용이 최신 공식 절차와
          일치하는지는 아직 확인 절차를 거치지 않았습니다. 통화 전 기관 홈페이지에서
          한 번 더 확인하세요.
        </p>
      ) : null}

      <ul className="flex flex-col gap-3">
        {items.map((item) => (
          <li key={item.id} className="text-body">
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <span className="font-medium text-foreground">{item.title}</span>
              {!item.verified ? (
                <span className="text-[0.6875rem] text-muted-foreground">
                  공식 확인 전
                </span>
              ) : null}
            </div>

            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-caption text-muted-foreground">
              <span>{item.publisher}</span>

              {item.phone ? (
                <a
                  href={`tel:${item.phone}`}
                  className="inline-flex min-h-8 items-center gap-1 font-medium text-primary underline underline-offset-2"
                >
                  <Phone aria-hidden className="size-3.5" />
                  {item.phone}
                </a>
              ) : null}

              {item.url ? (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex min-h-8 items-center gap-1 font-medium text-primary underline underline-offset-2"
                >
                  <ExternalLink aria-hidden className="size-3.5" />
                  홈페이지
                </a>
              ) : null}

              {item.fetchedAt ? <span>확인 {item.fetchedAt}</span> : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
