import type { Evidence } from "@/lib/api/contracts";

/**
 * mock 근거 목록.
 *
 * 중요: 존재하지 않는 기관·제도·전화번호를 만들어내지 않는다.
 * (CLAUDE.md — "Never fabricate products, rates, eligibility, laws,
 *  institutions, or official guidance")
 *
 * 아래 항목은 모두 실재하는 기관/창구를 가리키지만, 이번 작업에서 공식 출처를
 * 직접 조회해 확인한 것은 아니다. 따라서 전부 `verified: false` 로 두고
 * 화면에 "공식 확인 전"으로 표시한다. 백엔드 `/api/v1/evidence` 가 생기면
 * fetchedAt 과 함께 검증된 항목으로 대체된다.
 */
const UNVERIFIED_NOTE = "백엔드 근거 연동 전이라 공식 확인 절차를 거치지 않았습니다.";

export const MOCK_EVIDENCE: Record<string, Evidence> = {
  fss_1332: {
    id: "fss_1332",
    title: "불법사금융·보이스피싱 통합신고센터",
    publisher: "금융감독원",
    phone: "1332",
    note: UNVERIFIED_NOTE,
    verified: false,
  },
  police_112: {
    id: "police_112",
    title: "경찰 신고 (사기 피해·계좌 지급정지 요청)",
    publisher: "경찰청",
    phone: "112",
    note: UNVERIFIED_NOTE,
    verified: false,
  },
  kisa_118: {
    id: "kisa_118",
    title: "개인정보 침해·스미싱 신고 상담",
    publisher: "한국인터넷진흥원(KISA)",
    phone: "118",
    note: UNVERIFIED_NOTE,
    verified: false,
  },
  payinfo: {
    id: "payinfo",
    title: "계좌정보통합관리서비스 — 내 이름으로 열린 계좌 확인",
    publisher: "금융결제원",
    url: "https://www.payinfo.or.kr",
    note: UNVERIFIED_NOTE,
    verified: false,
  },
  msafer: {
    id: "msafer",
    title: "명의도용방지서비스 — 내 명의 휴대폰 개통 내역 확인",
    publisher: "한국정보통신진흥협회",
    url: "https://www.msafer.or.kr",
    note: UNVERIFIED_NOTE,
    verified: false,
  },
  kinfa_products: {
    id: "kinfa_products",
    title: "서민금융상품 기본정보 / 대출상품한눈에",
    publisher: "금융위원회 · 서민금융진흥원",
    note: `${UNVERIFIED_NOTE} 연동 예정 API 는 docs/07-official-api-candidates.md 참고.`,
    verified: false,
  },
};

export function evidenceByIds(ids: readonly string[]): Evidence[] {
  return ids
    .map((id) => MOCK_EVIDENCE[id])
    .filter((item): item is Evidence => Boolean(item));
}
