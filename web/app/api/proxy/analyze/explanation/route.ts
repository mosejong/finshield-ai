import { NextResponse } from "next/server";
import { AnalyzeRequestSchema } from "@/lib/api/contracts";
import { explainOnServer } from "@/lib/api/explanation";
import { backendHeaders } from "@/lib/api/server-auth";
import { upstreamStatus } from "@/lib/api/proxy-response";
import { readJsonBody } from "@/lib/api/request-body";

/**
 * "왜 위험한지" 설명을 받아오는 프록시.
 *
 * `/api/proxy/analyze` 와 나란히 두는 이유는 백엔드가 두 엔드포인트를 나눠 둔
 * 이유와 같다. 판정은 즉시 나오고 설명은 8초쯤 걸리므로, 하나로 합치면 판정
 * 표시가 설명을 기다리게 된다.
 *
 * 판정을 클라이언트가 실어 보내지 않는다는 점이 중요하다. 여기로 오는 것은
 * 원문뿐이고, 위험 수준·신호·행동은 백엔드가 다시 만든다. 그렇지 않으면
 * 클라이언트가 "위험 낮음" 을 보내 모델에게 안심시키는 문장을 쓰게 할 수 있다.
 *
 * 사용자가 입력한 원문은 여기서 로그로 남기지 않는다.
 * (docs/12-security-threat-model.md — log leakage)
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * 백엔드가 최악의 경우 20초까지 쓴다(주 모델 14초 + 대체 모델 6초). 플랫폼
 * 기본 실행 시간이 그보다 짧으면 정상 응답이 잘리므로 여유를 명시한다.
 */
export const maxDuration = 30;

export async function POST(request: Request) {
  const body = await readJsonBody(request);
  if (!body.ok) return body.response;

  const parsed = AnalyzeRequestSchema.safeParse(body.value);
  if (!parsed.success) {
    return NextResponse.json(
      { message: "설명할 내용을 확인하지 못했습니다." },
      { status: 400 },
    );
  }

  try {
    const explanation = await explainOnServer(parsed.data, backendHeaders(request));
    return NextResponse.json(explanation);
  } catch (error) {
    // 설명 실패는 분석 실패와 다르다. 판정은 이미 화면에 있으므로 여기서는
    // 사용자에게 보여줄 상세 문구를 만들지 않고 상태 코드만 정확히 남긴다.
    return NextResponse.json(
      { message: "설명을 불러오지 못했습니다." },
      { status: upstreamStatus(error) },
    );
  }
}
