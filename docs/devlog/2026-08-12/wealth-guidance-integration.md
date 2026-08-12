# Wealth Guidance v0.1 PM 통합 일지

- 작업일: 2026-08-12 (KST)
- 담당: PM / main 관리
- 브랜치: `docs/wealth-guidance-integration`
- 기준 main: `d2ce019` (`feat: add evidence-backed wealth guidance (#34)`)

## 병합 결과

- 기능 PR: [#34](https://github.com/mosejong/finshield-ai/pull/34)
- 기능 병합 SHA: `d2ce019`
- 방식: squash merge
- GitHub Actions backend `test`, frontend `web`: 최종 통과
- 병합 후 main 동기화: 완료

## PM 문서 반영

- README 테스트 기준을 Python 143 passed, frontend 18 passed로 갱신
- API·화면·공식 source 무결성과 투자 조언 금지선을 기록
- P1 재테크 기초 가이드 v0.1을 완료 처리
- `docs/19-wealth-guidance.md`와 개발·통합 일지를 문서 색인에 추가

## 유지되는 경계와 후속 작업

- 현재 가이드는 입력 없는 일반 교육이며 개인별 투자 판단을 제공하지 않는다.
- 개인화가 필요해도 profile 구간을 backend에서 읽는 별도 계약과 근거 규칙이 먼저다.
- 계좌·보유종목·거래내역 수집, 상품·종목 추천, 수익률 예측은 MVP 범위 밖이다.
- 다음 제품 기능 후보는 공식 상품 상세·비교 또는 profile 영구 저장·인증 경계다.
