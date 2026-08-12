import Link from "next/link";
import type { NextAction, SourceKind } from "@/lib/api/contracts";
import { SectionHeading } from "@/components/common/SectionHeading";
import { MockBadge } from "@/components/common/MockBadge";

/** Home 블록 4 — 다음 행동. 한 번에 하나만 제안한다. */
export function NextActionBlock({
  action,
  source,
}: {
  action: NextAction | null;
  source: SourceKind;
}) {
  if (!action) return null;

  return (
    <section aria-labelledby="home-next">
      <SectionHeading badge={<MockBadge source={source} />}>
        <span id="home-next">다음 행동</span>
      </SectionHeading>

      <div className="rounded-lg border border-safe-border bg-safe-bg p-4">
        <p className="text-body font-medium text-foreground">{action.title}</p>
        <p className="mt-1 text-caption text-muted-foreground">
          {action.detail}
        </p>

        <Link
          href={action.href}
          className="mt-3 inline-flex min-h-11 items-center justify-center rounded-md bg-primary px-4 text-body font-semibold text-primary-foreground transition-opacity hover:opacity-90"
        >
          {action.ctaLabel}
        </Link>
      </div>
    </section>
  );
}
