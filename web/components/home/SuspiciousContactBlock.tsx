import Link from "next/link";
import { ChevronRight } from "lucide-react";
import type { AnalysisSummary, SourceKind } from "@/lib/api/contracts";
import { SectionHeading } from "@/components/common/SectionHeading";
import { MockBadge } from "@/components/common/MockBadge";
import { formatDateTime, riskStyle } from "@/lib/format/risk";

/**
 * Home 블록 3 — 위험한 금융 연락 확인.
 *
 * 이 블록은 프로필이 없어도 항상 동작해야 한다. 의심 문자를 방금 받은 사람에게
 * 온보딩을 먼저 요구하지 않는다는 IA 결정을 화면에서 지키는 자리다.
 */
export function SuspiciousContactBlock({
  recent,
  source,
}: {
  recent: AnalysisSummary[];
  source: SourceKind;
}) {
  return (
    <section aria-labelledby="home-suspicious">
      <SectionHeading>
        <span id="home-suspicious">위험한 금융 연락 확인</span>
      </SectionHeading>

      <Link
        href="/check"
        className="block rounded-lg border border-primary/25 bg-card p-4 transition-colors hover:bg-secondary"
      >
        <p className="text-body font-medium text-foreground">
          의심스러운 문자나 링크를 붙여넣어 보세요
        </p>
        <p className="mt-1 text-caption text-muted-foreground">
          어떤 부분이 정상 절차와 다른지, 지금 무엇을 하면 안 되는지 알려드립니다.
        </p>
        <span className="mt-3 inline-flex min-h-9 items-center gap-0.5 text-caption font-semibold text-primary">
          확인하기
          <ChevronRight aria-hidden className="size-3.5" />
        </span>
      </Link>

      {recent.length > 0 ? (
        <div className="mt-3">
          <p className="mb-2 flex items-center gap-1.5 text-caption text-muted-foreground">
            최근 확인한 연락
            <MockBadge source={source} />
          </p>

          <ul className="flex flex-col gap-2">
            {recent.map((item) => {
              const style = riskStyle(item.level);

              return (
                <li key={item.id}>
                  <Link
                    href={`/check/result/${item.id}`}
                    className="flex items-start gap-3 rounded-lg border border-border bg-card p-3 transition-colors hover:bg-secondary"
                  >
                    <span
                      aria-hidden
                      className={`mt-1.5 size-2 shrink-0 rounded-full ${style.dot}`}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-caption font-medium text-foreground">
                        <span className={style.text}>{style.label}</span>
                        <span className="text-muted-foreground"> · </span>
                        {item.excerpt}
                      </p>
                      <p className="mt-0.5 text-caption text-muted-foreground">
                        {formatDateTime(item.createdAt)}
                        {item.openActionCount > 0
                          ? ` · 남은 조치 ${item.openActionCount}개`
                          : ""}
                      </p>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
