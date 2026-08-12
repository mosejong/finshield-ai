# Product Recommendations UI v0.1 개발일지

- 작업일: 2026-08-12 (KST)
- 담당: frontend / PM integration
- 브랜치: `feature/product-recommendations-ui-v01`
- worktree: `C:\Users\user\Desktop\project\finshield-ai`
- 기준 main: `ee14cf22f754a517a896f520cf712dd2e00e6be9`

## 목표와 범위

- `/products` placeholder를 공식 recommendations live 화면으로 교체
- profile session에서 goal 하나만 전송
- backend status·reason·공식 원문을 재계산 없이 표시
- 상품 상세·비교·시뮬레이션은 비범위

## 구현

- zod backend 응답 계약과 business → startup_business goal adapter
- Next same-origin `/api/proxy/recommendations`
- profile 없음·loading·provider 실패·성공 상태
- 상태 집계, 공식 기준월, 상품명·기관·용도·금리·한도·대상 원문, reason, 출처
- 실패를 빈 목록 또는 이용 가능한 상품 없음으로 바꾸지 않음

## 최소수집

- 소득·부채·신용·연령은 서버로 전송하지 않는다.
- goal 하나만 전송하며 profile form 안내 문구도 실제 동작에 맞게 교정했다.
- 프록시는 request body를 로그로 남기지 않는다.

## 구현 중 수정

- 첫 build: 옛 placeholder를 부분 교체한 흔적으로 undefined symbol TypeScript 오류
- placeholder constant·숨김 markup을 완전히 제거해 교정
- 첫 검증 명령: PowerShell execution policy가 npm.ps1 차단
- 정책을 변경하지 않고 npm.cmd/npx.cmd로 실행
- sandbox 쓰기 제한으로 `.next`, tsbuildinfo, vite temp EPERM 발생 후 저장소 작업
  권한으로 동일 명령 재실행

## 검증

- Next build: 9 routes 통과 (`/api/proxy/recommendations` 포함)
- TypeScript: 통과
- lint: 통과
- 기존 vitest: 3 passed
- goal-only 전송과 502 실패 회귀 테스트 추가 후 전체 재검증 예정

## 최종 검증

- Next build·TypeScript·lint: 통과
- Vitest: **2 files, 5 passed**
- goal-only request와 502 비은폐 회귀: 통과
- 실제 Next proxy → FastAPI live E2E: 기준월 `202607`, 전체 325건,
  `potential_match` 44, `mismatch` 280, `needs_review` 1, 첫 100건 반환
- 임시 Next 서버는 검증 직후 종료
- `git diff --check`: 통과

## PM 리뷰 교정

- 목표 변경 직후 새 응답 전까지 이전 목표 결과가 잠깐 표시될 수 있는 상태 경계 발견
- async 응답 상태에 요청 goal을 태그하고 현재 session goal과 다르면 loading으로 처리
- 이전 goal 결과를 현재 goal 결과로 오인 표시하지 않도록 교정

## 병합

- PR: [#24 feat: connect official product recommendations UI](https://github.com/mosejong/finshield-ai/pull/24)
- 병합 커밋: `6b10ab754fa6f1a0258c4009b79be1fd0c2db772`
- 상태: 완료 — main 병합 및 PM 문서 통합

## 변경 파일

- `web/app/products/page.tsx`
- `web/app/api/proxy/recommendations/route.ts`
- `web/components/finance/ProductRecommendations.tsx`
- `web/components/finance/ProfileForm.tsx`
- `web/lib/api/contracts.ts`
- `web/lib/api/products.ts`
- `web/lib/api/products.test.ts`
- `docs/13-frontend-architecture.md`
- 본 개발일지
