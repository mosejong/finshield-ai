# Loan What-if UI PM 통합 일지

- 작업일: 2026-08-12 (KST)
- 담당: PM / main 관리
- 브랜치: `docs/loan-what-if-integration`
- 기준 main: `a93d874` (`feat: add loan what-if comparison UI (#32)`)

## 병합 결과

- 기능 PR: [#32](https://github.com/mosejong/finshield-ai/pull/32)
- 기능 병합 SHA: `a93d874`
- 방식: squash merge
- GitHub Actions backend `test`, frontend `web`: 최종 통과
- 병합 후 main 동기화: 완료

## PM 문서 반영

- README frontend 테스트 기준을 16 passed로 갱신
- `/products/simulate`의 입력·표시·실패 경계와 공식 상환표 아님을 기록
- P1 What-if loan simulation을 완료 처리
- 남은 상품 상세·공식 상품 비교와 재테크 기초 가이드를 다음 우선순위로 분리
- 문서 색인에 기능 개발일지와 본 통합 일지를 추가

## 다음 작업: 재테크 기초 가이드

사용자 요구를 다음 기능으로 확정한다. 공식 교육 자료를 설명 근거로 연결하되
FinShield가 투자상품이나 매매 시점을 추천하는 서비스로 확장되지는 않는다.

- 순서: 현금흐름 확인 → 비상자금 확인 → 부채 부담 확인 → 투자 위험 이해
- 제공: 일반 금융교육, 분산의 의미, 공식 학습 링크, profile 구간 기반 확인 항목
- 금지: 종목·코인·ETF 선택, 수익률 예측, 매수·매도 시점, 원금·수익 보장
- 데이터 최소화: 기존 profile 구간값과 goal만 사용하고 계좌·보유종목은 받지 않음
- 근거: 서민금융진흥원 금융교육/비대면 금융교육, 전국투자자교육협의회

구현 전에 문장별 공식 근거와 deterministic 상태 규칙을 별도 설계 문서로 고정한다.
