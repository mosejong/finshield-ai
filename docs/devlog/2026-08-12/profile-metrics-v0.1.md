# Profile Metrics v0.1 개발일지

- 작업일: 2026-08-12 (KST)
- 담당: backend / frontend / PM
- 브랜치: `feature/profile-metrics-v01`
- 기준 main: `1583d47`

## 목표

- `/profile`의 준비 중 지표를 backend 결정론적 계산으로 교체
- 기존 문서에 정의된 월 현금흐름·월소득 대비 상환액·비상자금 기간만 구현
- 공식 DSR·대출 심사·투자 추천과 명확히 구분
- 추가 개인정보 수집이나 브라우저 profile 원문 저장 없음

## 설계 결정

- profile metrics는 저장하지 않고 현재 profile을 읽어 요청 시 계산한다.
- 0으로 나누는 입력은 0이나 무한대로 추정하지 않고 계산 불가로 반환한다.
- 임의의 금융 건전성 임계값을 만들지 않고 적자와 사용자 목표 달성 여부만 tone에 사용한다.
- 계산 원값과 profile updated_at을 응답해 재현·감사 경계를 유지한다.

## 구현

- 순수 Decimal 기반 `calculate_profile_metrics` 도메인 계산기
- `GET /api/v1/profiles/{profile_id}/metrics`
- 표시용 3개 지표와 별도 계산 원값, 가정, disclaimer 계약
- 정상·반올림·0 분모·404·OpenAPI 회귀 테스트
- Next profile metrics proxy와 strict zod 계약
- `/profile` summary·3개 지표·계산 기준·backend disclaimer live 연결

## 실브라우저 1차 검수

- profile 저장과 backend metrics 200 응답은 성공했지만 Next strict schema가 첫 지표의
  `caveat: null`을 거절해 502가 되는 계약 불일치를 발견했다.
- 모든 지표에 실제 계산 제외 범위를 담은 caveat 문자열을 제공해 null/optional 모호성을
  제거하고, 세 지표 모두 caveat가 있는지 회귀 테스트를 추가했다.

## 범위 확장

- 같은 metrics API를 Home의 첫 블록에도 연결해 mock 금융상태 요약을 제거했다.
- Home은 브라우저에 저장된 profile ID로 서버 profile과 metrics를 읽으며 계산은 하지 않는다.
- profile 미입력·로딩·지표 실패 상태를 각각 명시하고 다른 mock 블록과 source badge를 섞지 않는다.
- 실데이터 5.6개월과 Home mock 2.4개월이 동시에 노출되는 모순을 발견해 Home의 가짜
  개인화 카드·다음 행동·최근 분석 이력을 제거했다.
- 지금 확인할 정보와 다음 행동은 저장 profile의 goal 및 구현된 공식 상품 화면으로만
  연결하고, 분석 이력 저장 기능이 없으므로 예시 이력을 실제 최근 기록처럼 표시하지 않는다.

## PM 재검수

- 반올림된 비상자금 기간이 목표와 같아 보여도 실제 금액이 1원이라도 부족하면 달성으로
  바뀌지 않도록 tone은 표시 개월이 아니라 정확한 목표 부족액으로 결정한다.
- Home profile 로딩 중 온보딩 미완료 안내가 잠깐 보이지 않도록 개인화 블록은 로딩 완료 후 표시한다.

## 최종 검증

- Python 3.12.10 `pytest -q`: 158 passed, 기존 TestClient 중단 예정 경고 1건
- frontend `vitest`: 8 files / 24 tests passed
- `eslint`, `tsc --noEmit`, Next production build: 통과
- 실브라우저 profile 입력: 1,450,000원 / 7.1% / 5.6개월과 backend summary 일치
- 계산 기준·세 지표 caveat·공식 DSR 아님 disclaimer 표시 확인
- Home live 요약 동일 값 확인, 과거 2.4개월 mock·가짜 최근 분석 제거 확인
- 0원 분모는 도메인/API 회귀 테스트에서 두 지표 `null` / `계산 불가` 확인
- 반응형 375 / 768 / 1280px 가로 overflow 없음
- `git diff --check`: 통과

## PR·PM 리뷰

- 2026-08-13 PR #38의 test·web CI 4개가 모두 통과했다.
- PM 재검수에서 계산 원값과 표시값 분리, 0 분모 null 경계, profile 404,
  Home 로딩·미입력·실패 상태, mock 제거 범위를 다시 확인했다.
- 공식 DSR·대출 승인·투자 적합성 판단을 만들지 않고, 추가 개인정보 필드와
  계산 결과 영구 저장도 추가하지 않았음을 확인했다.
