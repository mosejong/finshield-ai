import Link from "next/link";
import { ChevronRight } from "lucide-react";
import type { FinancialSnapshot } from "@/lib/api/contracts";
import { SectionHeading } from "@/components/common/SectionHeading";
import { MockBadge } from "@/components/common/MockBadge";

/** Home 블록 1 — 현재 금융상태. 숫자 나열이 아니라 한 문장이 먼저 온다. */
export function FinancialStatusBlock({
  snapshot,
}: {
  snapshot: FinancialSnapshot;
}) {
  return (
    <section aria-labelledby="home-status">
      <SectionHeading badge={<MockBadge source={snapshot.source} />}>
        <span id="home-status">현재 금융상태</span>
      </SectionHeading>

      <Link
        href={snapshot.hasProfile ? "/profile" : "/onboarding"}
        className="block rounded-lg border border-border bg-card p-4 transition-colors hover:bg-secondary"
      >
        <p className="text-body text-foreground">{snapshot.summary}</p>

        {snapshot.metrics.length > 0 ? (
          <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-border pt-3">
            {snapshot.metrics.map((metric) => (
              <div key={metric.key}>
                <dt className="text-caption text-muted-foreground">
                  {metric.label}
                </dt>
                <dd className="mt-0.5 text-title text-foreground">
                  {metric.display}
                </dd>
              </div>
            ))}
          </dl>
        ) : null}

        <span className="mt-3 inline-flex items-center gap-0.5 text-caption font-medium text-primary">
          {snapshot.hasProfile ? "자세히 보기" : "금융상태 알려주기"}
          <ChevronRight aria-hidden className="size-3.5" />
        </span>
      </Link>
    </section>
  );
}
