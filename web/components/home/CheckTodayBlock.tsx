import Link from "next/link";
import { ChevronRight } from "lucide-react";
import type { CheckItem, SourceKind } from "@/lib/api/contracts";
import { SectionHeading } from "@/components/common/SectionHeading";
import { MockBadge } from "@/components/common/MockBadge";

/** Home 블록 2 — 지금 확인할 금융정보 */
export function CheckTodayBlock({
  items,
  source,
}: {
  items: CheckItem[];
  source: SourceKind;
}) {
  return (
    <section aria-labelledby="home-check">
      <SectionHeading badge={<MockBadge source={source} />}>
        <span id="home-check">지금 확인할 금융정보</span>
      </SectionHeading>

      {items.length === 0 ? (
        <p className="rounded-lg border border-border bg-card p-4 text-body text-muted-foreground">
          금융상태를 알려주시면 상황에 맞는 정보를 골라 보여드립니다.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li key={item.id}>
              <Link
                href={item.href}
                className="flex items-start gap-3 rounded-lg border border-border bg-card p-4 transition-colors hover:bg-secondary"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-body font-medium text-foreground">
                    {item.title}
                  </p>
                  <p className="mt-1 text-caption text-muted-foreground">
                    {item.reason}
                  </p>
                  {item.evidence ? (
                    <p className="mt-2 text-caption text-muted-foreground">
                      출처 {item.evidence.publisher}
                      {item.evidence.verified ? "" : " · 공식 확인 전"}
                    </p>
                  ) : null}
                </div>
                <ChevronRight
                  aria-hidden
                  className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
