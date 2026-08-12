# Loan What-if UI v0.1 개발일지

- 작업일: 2026-08-12 (KST)
- 담당: frontend / PM
- 브랜치: `feature/loan-what-if-ui-v01`
- worktree: `C:\Users\user\Documents\Codex\finshield-ai-main`
- 기준 main: `98e618ae2c3c349e183bcbfcaf72252063a3dd22`

## 목표와 범위

- `/products/simulate`에서 현재 금리와 바꾼 금리의 대출 상환 결과를 나란히 비교
- 브라우저는 계산하지 않고 두 조건을 각각 `POST /api/v1/loans/simulate`에 전달
- 월 납입액·총 상환액·총 이자·상환 일정은 backend 결과만 표시
- 금융기관별 실제 일수 계산, 납입일, 거치기간, 중도상환수수료는 비범위
- 공식 상품의 적격성·금리와 자동 연결하는 상품 비교 화면은 비범위

## 안전선

- 한쪽 계산이 실패하면 두 결과 모두 숨기고 실패를 명시한다.
- 프론트에서 두 결과의 차액이나 절감액을 계산하지 않는다.
- 원금균등은 고정 월 납입액이 없으므로 첫 달·마지막 달 납입액을 backend 일정에서 표시한다.
- 결과는 금융기관의 공식 상환표가 아닌 의사결정 지원용 비교값임을 고지한다.

## 예정 변경 파일

- `web/app/products/page.tsx`
- `web/app/products/simulate/page.tsx`
- `web/app/api/proxy/loans/simulate/route.ts`
- `web/components/finance/LoanWhatIf.tsx`
- `web/lib/api/contracts.ts`
- `web/lib/api/loans.ts`, `web/lib/api/loans.test.ts`
- `docs/13-frontend-architecture.md`
- 본 개발일지

## 구현

- 단일 backend 계약을 검증하는 Next same-origin proxy 추가
- current·alternative를 동시에 요청하되 한쪽 실패를 숨기지 않는 API adapter 추가
- 원금·두 금리·기간·상환방식 입력과 backend 결과 카드 구현
- 원리금균등은 정기 월 납입액, 원금균등은 첫 달 납입액으로 라벨을 구분
- 마지막 달 납입액·총이자·총상환액·첫 회차 원금/이자를 backend 값 그대로 표시
- `/products`에 시뮬레이션 진입점 추가

## 실제 브라우저 검수 중 수정

- 최초 클릭에서 원금 `min=0.01`, `step=10000` 조합 때문에 기본값 1,000만 원을
  브라우저가 step 불일치로 거부하는 문제를 발견했다.
- 원 단위 입력 계약에 맞게 `min=1`, `step=1`로 교정했다. 큰 금액의 빠른 입력은
  짧은 금액 표시 힌트로 확인한다.

## 검증

- Vitest: **5 files, 16 passed**
- ESLint: 통과
- TypeScript: 통과
- Next production build: 통과, `/products/simulate`와 proxy 포함
- Python 3.12.10 `pytest -q`: **139 passed**
- Python 3.8.10 기본 실행은 프로젝트 지원 버전이 아니어서 collection 실패 확인;
  호환 코드는 추가하지 않고 프로젝트 `.venv`의 3.12.10으로 재검증
- live Next → FastAPI: 1,000만 원·36개월·5.5% 대 4.0% 원리금균등 결과 확인
- 원금균등: 고정 월 납입액 대신 두 카드 모두 첫 달·마지막 달 납입액 표시 확인
- 브라우저 console error: 0건
- 375 / 768 / 1280px: 가로 overflow 없음, 768px 결과 2열, 1280px SideNav 확인
- 375px full-page 캡처는 글자가 세로로 보이는 캡처 아티팩트가 있었으나 같은 상태의
  viewport 캡처와 DOM 실제 폭(본문 343px, document 375px)으로 정상 레이아웃 확인

## PR 및 PM 검수

- Draft PR: [#32 feat: add loan what-if comparison UI](https://github.com/mosejong/finshield-ai/pull/32)
- GitHub Actions backend `test`, frontend `web`: 통과
- PM 계약 검수: 프론트 이자·차액 계산 없음, request 최소 필드, 양쪽 실패 비은폐 확인
- PM 표현 검수: 원금균등의 `monthly_payment=null`을 첫 달 납입액으로 정확히 표시
- PM 사용성 검수: 브라우저에서 발견한 원금 step 불일치를 병합 전 교정
- 차단 이슈: 없음

## 후속 요구사항: 재테크 기초 가이드

사용자 요청으로 재테크 관심 사용자를 위한 교육 기능을 다음 단계 후보로 등록한다.
서민금융진흥원의 재무설계·저축과 소비·부채관리·자산형성 및 투자 교육 체계와
전국투자자교육협의회의 투자 기초·분산·자기판단 원칙을 공식 근거로 사용한다.

- 포함: 현금흐름, 비상자금, 고금리 부채, 투자 위험 이해, 분산의 의미, 공식 교육 링크
- 제외: 종목·코인 추천, 목표수익률 보장, 매수·매도 시점, 성향을 넘는 개인화 투자판단
- 개인화 입력: 기존 profile의 구간값과 목표만 사용하고 정확한 자산내역은 추가 수집하지 않음

공식 근거:

- 서민금융진흥원 금융교육: https://www.kinfa.or.kr/financialLife/financialEducation.do
- 서민금융진흥원 비대면 금융교육: https://www.kinfa.or.kr/fill4young/education/onlineEducation.do
- 전국투자자교육협의회 소개: https://www.kcie.or.kr/mobile/intro/introduce
