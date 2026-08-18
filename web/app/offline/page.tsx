import type { Metadata } from "next";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { SectionHeading } from "@/components/common/SectionHeading";

/**
 * 오프라인 대체 화면. 서비스 워커가 네트워크 실패한 화면 이동을 여기로 돌린다.
 *
 * "인터넷에 연결되어 있지 않습니다" 한 줄만 띄우고 끝내지 않는다. 이 화면을 보는
 * 사람은 방금 수상한 문자를 받고 확인하려던 참일 가능성이 높고, 그 상태에서
 * 아무것도 없는 화면을 보면 그냥 링크를 눌러 볼 수 있다. 연결이 없어도 유효한
 * 조치 - 누르지 않기, 공식 대표번호로 직접 확인하기, 전화 신고 - 를 함께 둔다.
 * 전화는 데이터가 끊겨도 걸린다.
 *
 * 확인하지 못한 것을 안전으로 읽히게 두지 않는다 (docs/13 — 공포 유발 없이,
 * 그러나 안전을 단정하지도 않기).
 */

export const metadata: Metadata = {
  title: "연결 없음",
  description: "인터넷에 연결되어 있지 않을 때 볼 수 있는 안내입니다.",
};

const HOTLINES = [
  {
    phone: "112",
    label: "경찰",
    note: "이미 돈을 보냈거나 계좌·인증정보를 넘겼다면 가장 먼저.",
  },
  {
    phone: "1332",
    label: "금융감독원",
    note: "불법사금융·보이스피싱 통합신고센터.",
  },
  {
    phone: "118",
    label: "한국인터넷진흥원",
    note: "개인정보 침해·스미싱 신고 상담.",
  },
];

export default function OfflinePage() {
  return (
    <AppShell>
      <PageHeader
        title="지금은 인터넷에 연결되어 있지 않습니다"
        description="연결이 돌아오면 받은 내용을 다시 확인해 드릴 수 있습니다."
      />

      <div
        role="note"
        className="mb-7 rounded-lg border-l-4 border-risk-medium border-y border-r border-risk-medium-border bg-risk-medium-bg p-4"
      >
        <p className="text-body text-foreground">
          확인하지 못했다는 것이 안전하다는 뜻은 아닙니다. 연결이 없는 동안에는
          아래 원칙만 지켜 주세요.
        </p>
      </div>

      <section aria-labelledby="offline-actions" className="mb-7">
        <SectionHeading>
          <span id="offline-actions">연결이 없어도 지금 할 수 있는 것</span>
        </SectionHeading>

        <ol className="flex flex-col gap-3">
          {[
            "메시지에 있는 링크를 누르지 않습니다. 확인 전에는 열지 않는 편이 항상 낫습니다.",
            "계좌번호, 인증번호, 비밀번호, 신분증 사진을 보내지 않습니다. 정상 절차에서는 요구하지 않습니다.",
            "상대가 말한 기관이 맞는지 확인할 때는 메시지에 적힌 번호가 아니라, 직접 찾은 공식 대표번호로 겁니다.",
          ].map((step, index) => (
            <li
              key={step}
              className="flex gap-3 rounded-lg border border-border bg-card p-4"
            >
              <span
                aria-hidden
                className="flex size-6 shrink-0 items-center justify-center rounded-full bg-secondary text-caption font-semibold tabular-nums text-foreground"
              >
                {index + 1}
              </span>
              <p className="text-body text-foreground">{step}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="offline-hotlines" className="mb-7">
        <SectionHeading>
          <span id="offline-hotlines">전화로 연결되는 공식 창구</span>
        </SectionHeading>
        <p className="mb-3 text-caption text-muted-foreground">
          데이터가 끊겨 있어도 전화는 걸립니다.
        </p>

        <ul className="flex flex-col gap-2">
          {HOTLINES.map((hotline) => (
            <li key={hotline.phone}>
              <a
                href={`tel:${hotline.phone}`}
                className="flex min-h-14 items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:bg-secondary"
              >
                <span className="text-body font-semibold tabular-nums text-primary">
                  {hotline.phone}
                </span>
                <span className="min-w-0">
                  <span className="block text-body text-foreground">
                    {hotline.label}
                  </span>
                  <span className="block text-caption text-muted-foreground">
                    {hotline.note}
                  </span>
                </span>
              </a>
            </li>
          ))}
        </ul>
      </section>

      <Link
        href="/check"
        className="inline-flex min-h-12 w-full items-center justify-center rounded-md bg-primary px-4 text-body font-semibold text-primary-foreground transition-opacity hover:opacity-90"
      >
        다시 시도하기
      </Link>
    </AppShell>
  );
}
