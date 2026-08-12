"use client";

import { useEffect, useState } from "react";
import { Check, ExternalLink } from "lucide-react";
import { DisclaimerNote } from "@/components/common/DisclaimerNote";
import { fetchWealthGuidance } from "@/lib/api/wealth";
import type { WealthGuidanceResponse } from "@/lib/api/contracts";


export function WealthGuidance() {
  const [data, setData] = useState<WealthGuidanceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchWealthGuidance()
      .then((guidance) => {
        if (active) setData(guidance);
      })
      .catch(() => {
        if (active) {
          setError(
            "공식 금융교육 정보를 불러오지 못했습니다. 가이드가 보이지 않는다고 투자 위험이 없다는 뜻은 아닙니다.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, []);

  if (error) {
    return (
      <p
        role="alert"
        className="rounded-lg border border-risk-medium-border bg-risk-medium-bg p-4 text-body text-risk-medium"
      >
        {error}
      </p>
    );
  }

  if (!data) {
    return <p className="text-body text-muted-foreground">공식 금융교육을 확인하고 있습니다…</p>;
  }

  const sourcesById = new Map(
    data.official_sources.map((source) => [source.source_id, source]),
  );

  return (
    <>
      <p className="rounded-lg border border-safe-border bg-safe-bg p-4 text-body text-safe">
        투자상품을 고르기 전에 현재 금융생활과 위험을 이해하기 위한 4단계입니다.
      </p>

      <ol className="mt-4 flex flex-col gap-4">
        {data.modules.map((module) => (
          <li key={module.code} className="rounded-xl border border-border bg-card p-4">
            <p className="text-caption font-medium text-primary">{module.order}단계</p>
            <h2 className="mt-1 text-title text-foreground">{module.title}</h2>
            <p className="mt-2 text-body text-muted-foreground">{module.summary}</p>

            <h3 className="mt-4 text-body font-semibold text-foreground">스스로 확인할 질문</h3>
            <ul className="mt-2 flex flex-col gap-2">
              {module.check_questions.map((question) => (
                <li key={question} className="flex gap-2 text-body text-foreground">
                  <Check aria-hidden className="mt-1 size-4 shrink-0 text-safe" />
                  <span>{question}</span>
                </li>
              ))}
            </ul>

            <div className="mt-4 rounded-lg bg-muted p-3">
              <p className="text-caption font-medium text-foreground">다음 학습 행동</p>
              <p className="mt-1 text-body text-muted-foreground">{module.next_action}</p>
            </div>

            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
              {module.source_ids.map((sourceId) => {
                const source = sourcesById.get(sourceId);
                if (!source) return null;
                return (
                  <a
                    key={sourceId}
                    href={source.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex min-h-11 items-center gap-1 text-caption font-medium text-primary underline underline-offset-2"
                  >
                    {source.title} 근거
                    <ExternalLink aria-hidden className="size-3.5" />
                  </a>
                );
              })}
            </div>
          </li>
        ))}
      </ol>

      <section className="mt-6" aria-labelledby="wealth-sources-title">
        <h2 id="wealth-sources-title" className="text-title text-foreground">확인한 공식 자료</h2>
        <ul className="mt-3 flex flex-col gap-2">
          {data.official_sources.map((source) => (
            <li key={source.source_id} className="rounded-lg border border-border bg-card p-3">
              <a
                href={source.source_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex min-h-11 items-center gap-1 text-body font-medium text-primary underline underline-offset-2"
              >
                {source.title}
                <ExternalLink aria-hidden className="size-4" />
              </a>
              <p className="text-caption text-muted-foreground">
                {source.organization} · 확인일 {source.retrieved_at}
              </p>
            </li>
          ))}
        </ul>
      </section>

      <DisclaimerNote>{data.scope_disclaimer}</DisclaimerNote>
    </>
  );
}
